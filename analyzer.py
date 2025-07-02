import aiohttp
from typing import Optional, Tuple

async def query_lichess_analysis(fen: str) -> Optional[dict]:
    url = f"https://lichess.org/api/cloud-eval?fen={fen}&multiPv=3"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None

def evaluate_move(score_before: float, score_after: float, color: str) -> str:
    delta = score_after - score_before if color == "white" else score_before - score_after
    if delta >= 150:
        return "Brillant"
    elif delta >= 80:
        return "Très bon coup"
    elif delta >= 20:
        return "Bon coup"
    elif -20 <= delta < 20:
        return "Coup neutre"
    elif -80 <= delta < -20:
        return "Inexact"
    elif -150 <= delta < -80:
        return "Erreur"
    else:
        return "Gaffe"

async def analyze_fen_sequence(fen_before: str, fen_after: str, color: str) -> Optional[Tuple[str, str]]:
    eval_before = await query_lichess_analysis(fen_before)
    eval_after = await query_lichess_analysis(fen_after)
    if not eval_before or not eval_after:
        return None
    try:
        score_before = eval_before["pvs"][0]["cp"]
        score_after = eval_after["pvs"][0]["cp"]
    except (KeyError, IndexError):
        return None
    annotation = evaluate_move(score_before, score_after, color)
    return annotation, f"{score_before} → {score_after}"