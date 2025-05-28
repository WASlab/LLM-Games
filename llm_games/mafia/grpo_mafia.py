"""
Pure **Dr.GRPO** trainer for MafiaSim with Gemma‑27B FP8 on one H100.
All blocking environment roll‑outs are executed in a *separate* asyncio
ProcessPool so the GPU never idles.  vLLM is asked to return **G completions in
one call**, and log‑probabilities for the whole group are computed in a single
batched forward pass.

Major diffs versus v1
---------------------
* **Asynchronous roll‑out pool** (`aioprocessing.AioPool`) – learner queues
  `(state_hash, completion)` jobs; results return via `asyncio.Queue`.
* **Group sampling in one shot** – `SamplingParams(n=group_size)`.
* **Batched log‑prob calculation** for the whole group.
* **Stable model access** – use vLLM public API (`engine.backend_model`) instead
  of deep private chains.
* **FP8 autocast + Accelerator.prepare()** so *training* also runs fp8 on H100.
* **True PPO ratio**; we stash `logp_old` next to each completion.
* Full YAML I/O stub calls (`to_yaml` / `from_yaml`) remain.

This file assumes you have already migrated your MafiaEnv and YAML helpers to
FP8‑safe Torch & dataclass pickling.
"""
from __future__ import annotations
import asyncio, concurrent.futures, math, os, random, uuid
from dataclasses import dataclass
from typing import List

import torch, yaml
from torch import nn, optim
from accelerate import Accelerator
from rich.console import Console

from vllm import LLM, SamplingParams

from llm_games.mafia.env import MafiaEnv
from llm_games.mafia.yaml_io import to_yaml

console = Console()

# ----------------------------------------------------------------------------
# Dataclasses passed through queues
# ----------------------------------------------------------------------------
@dataclass
class PromptReq:
    pid: str
    prompt: str
    state_hash: bytes

@dataclass
class RollReq:
    pid: str
    completion: str
    logp_old: float
    state_hash: bytes

@dataclass
class RollRes:
    pid: str
    completion: str
    logp_old: float
    reward: float

# ----------------------------------------------------------------------------
# vLLM backend (one global instance)
# ----------------------------------------------------------------------------
class VllmGen:
    def __init__(self, model_path: str, context_len: int, temperature: float, group: int):
        self.llm = LLM(model_path, dtype="fp8_e4m3fn", max_model_len=context_len)
        self.params = SamplingParams(
            n=group,
            temperature=temperature,
            top_p=0.9,
        )
        self.tokenizer = self.llm.get_tokenizer()

    async def sample_group(self, prompt: str) -> List[str]:
        loop = asyncio.get_running_loop()
        outs = await loop.run_in_executor(None, lambda: self.llm.generate([prompt], self.params)[0])
        return [o.text for o in outs.outputs]

    def batch_logp(self, completions: List[str]):
        # batch compute log prob under *current* policy
        toks = self.tokenizer(completions, return_tensors="pt", padding=True).to("cuda")
        with torch.no_grad(), torch.autocast("cuda", torch.float8_e4m3fn):
            logits = self.llm.engine.backend_model(**toks).logits
        lp = torch.log_softmax(logits[:, :-1], dim=-1)
        gather_ids = toks.input_ids[:, 1:]
        lp_tok = lp.gather(2, gather_ids.unsqueeze(2)).squeeze(2)
        mask = (gather_ids != self.tokenizer.pad_token_id)
        logp_seq = (lp_tok * mask).sum(1)
        return logp_seq.tolist()

# ----------------------------------------------------------------------------
# Learner – runs on GPU only
# ----------------------------------------------------------------------------
class Learner:
    def __init__(self, model_path: str, G: int, lr=1e-5):
        self.G = G
        self.gen = VllmGen(model_path, 2048, temperature=0.7, group=G)
        self.model = self.gen.llm.engine.backend_model  # torch nn.Module
        self.opt = optim.AdamW(self.model.parameters(), lr=lr)
        self.acc = Accelerator()
        self.model, self.opt = self.acc.prepare(self.model, self.opt)
        self.buckets = {}

    async def handle_prompt(self, preq: PromptReq, rqueue: asyncio.Queue, rollpool):
        comps = await self.gen.sample_group(preq.prompt)
        logps = self.gen.batch_logp(comps)
        for c, lp in zip(comps, logps):
            # off‑load rollout to process pool (blocking env)
            await rollpool.coro_apply_async(run_rollout, RollReq(preq.pid, c, lp, preq.state_hash), rqueue)

    async def maybe_update(self, bucket: List[RollRes]):
        # compute advantage
        rewards = torch.tensor([b.reward for b in bucket], dtype=torch.float32)
        adv = (rewards - rewards.mean()) / (rewards.std() + 1e-6)
        logp_old = torch.tensor([b.logp_old for b in bucket], dtype=torch.float32, device=self.acc.device)
        # recompute logp_new in one batch
        logp_new = torch.tensor(self.gen.batch_logp([b.completion for b in bucket]), dtype=torch.float32, device=self.acc.device)
        ratio = torch.exp(logp_new - logp_old.to(self.acc.device))
        adv = adv.to(self.acc.device)
        eps = 0.2
        surr1 = ratio * adv
        surr2 = torch.clamp(ratio, 1 - eps, 1 + eps) * adv
        loss = -torch.min(surr1, surr2).mean()
        self.opt.zero_grad()
        self.acc.backward(loss)
        self.opt.step()

# ----------------------------------------------------------------------------
# Blocking rollout executed in a ProcessPool
# ----------------------------------------------------------------------------

def run_rollout(req: RollReq) -> RollRes:
    env = MafiaEnv.load_from_hash(req.state_hash)
    obs, _, done, _ = env.step(req.completion)
    while not done:
        pid = env.current_player
        act = env.policy_other(obs) if not env.is_learning_agent(pid) else env.policy_deterministic(obs)
        obs, _, done, _ = env.step(act)
    reward = 1.0 if env.learning_agent_won else 0.0
    return RollRes(req.pid, req.completion, req.logp_old, reward)

# ----------------------------------------------------------------------------
# Actor coroutines – produce prompts
# ----------------------------------------------------------------------------
async def actor(wid: int, pqueue: asyncio.Queue, learner_agents: List[str]):
    rng = random.Random(wid)
    while True:
        env = MafiaEnv(seed=rng.randint(0, 2**32 - 1))
        obs = env.reset()
        done = False
        while not done:
            if env.current_player in learner_agents:
                state_hash = env.save_state()
                pid = uuid.uuid4().hex
                await pqueue.put(PromptReq(pid, to_yaml(obs), state_hash))
                # learner will restore state; for live game we just pick deterministic stub
                obs, _, done, _ = env.step(env.policy_deterministic(obs))
            else:
                obs, _, done, _ = env.step(env.policy_other(obs))

# ----------------------------------------------------------------------------
# Main event loop
# ----------------------------------------------------------------------------
async def main():
    G = 3
    actors = 32
    model_path = os.getenv("GEMMA27_PATH", "./gemma-27b")

    pqueue: asyncio.Queue = asyncio.Queue(maxsize=actors * 4)
    rqueue: asyncio.Queue = asyncio.Queue()

    learner = Learner(model_path, G)
    # ProcessPool for CPU rollouts
    rollpool = concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count())
    rollpool = aioprocessing.AioPool(rollpool)

    # launch actors
    for wid in range(actors):
        asyncio.create_task(actor(wid, pqueue, learner_agents=["agent0"]))

    console.print("[green]Loop started – generating prompts …[/green]")

    while True:
        # dispatch prompt to learner
        preq = await pqueue.get()
        asyncio.create_task(learner.handle_prompt(preq, rqueue, rollpool))

        # receive rollout results and bucket
        try:
            res: RollRes = rqueue.get_nowait()
        except asyncio.QueueEmpty:
            continue
        bucket = learner.buckets.setdefault(res.pid, [])
        bucket.append(res)
        if len(bucket) == G:
            await learner.maybe_update(bucket)
            del learner.buckets[res.pid]

if __name__ == "__main__":
    import aioprocessing  # needs yum install aioprocessing
    asyncio.run(main())
