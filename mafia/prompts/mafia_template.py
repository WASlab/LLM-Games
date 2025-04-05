def format_prompt(name: str, obs: dict) -> str:
    # Format as readable context for the agent
    lines = [f"Day {obs['day']} | Phase: {obs['phase']}"]
    lines.append("Alive: " + ", ".join(obs["alive"]))
    lines.append("Dead: " + ", ".join(obs["dead"]))
    lines.append("Messages:")
    lines.extend(obs["messages"])
    lines.append("What do you do next? Choose one action:")
    return "\n".join(lines)

def parse_response(response: str) -> dict:
    """
    Expects LLM to return something like:
    <action> accuse </action> <target> Player3 </target>
    """
    import re
    act = re.search(r"<action>(.*?)</action>", response)
    tgt = re.search(r"<target>(.*?)</target>", response)
    return {
        "action": act.group(1).strip().lower() if act else "pass",
        "target": tgt.group(1).strip() if tgt else None
    }
