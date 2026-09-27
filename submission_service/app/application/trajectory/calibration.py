from dataclasses import dataclass

from submission_service.app.application.trajectory.knowledge import BktParams


MASTERY = 0.95
GAP = 0.5


@dataclass(frozen=True, slots=True)
class Calibration:
    params: BktParams
    margin: float
    margins: dict[str, float]


def readiness_threshold(pass_score: int = 8) -> float:
    return (pass_score - 1.5) / 9.0


def constraint_margins(params: BktParams, pass_score: int = 8) -> dict[str, float]:
    s, g, t, l0 = params.p_slip, params.p_guess, params.p_learn, params.p_init
    r_star = readiness_threshold(pass_score)
    p1 = _success(l0, s, g, t)
    p2 = _success(p1, s, g, t)
    p3 = _success(p2, s, g, t)
    f1 = _failure(l0, s, g, t)
    return {
        "C1": _predict(p1, s, g) - r_star,
        "C2": MASTERY - p2,
        "C3": p3 - MASTERY,
        "C4": GAP - f1,
        "C5": r_star - _predict(l0, s, g),
        "C6": _slip(p3, s, g) - 0.5,
        "C7": 0.5 - _slip(p1, s, g),
    }


def calibrate(pass_score: int = 8) -> Calibration:
    best: Calibration | None = None
    for l0 in _grid(0.10, 0.50, 0.05):
        for t in _grid(0.05, 0.40, 0.05):
            for s in _grid(0.05, 0.20, 0.05):
                for g in _grid(0.05, 0.35, 0.05):
                    params = BktParams(p_init=l0, p_learn=t, p_slip=s, p_guess=g)
                    margins = constraint_margins(params, pass_score)
                    margin = min(margins.values())
                    if margin <= 0:
                        continue
                    if best is None or margin > best.margin + 1e-9:
                        best = Calibration(params=params, margin=margin, margins=margins)
    if best is None:
        raise ValueError("Ограничения калибровки несовместны")
    return best


def _success(p: float, s: float, g: float, t: float) -> float:
    q = p * (1 - s) / (p * (1 - s) + (1 - p) * g)
    return q + (1 - q) * t


def _failure(p: float, s: float, g: float, t: float) -> float:
    q = p * s / (p * s + (1 - p) * (1 - g))
    return q + (1 - q) * t


def _slip(p: float, s: float, g: float) -> float:
    return p * s / (p * s + (1 - p) * (1 - g))


def _predict(p: float, s: float, g: float) -> float:
    return p * (1 - s) + (1 - p) * g


def _grid(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [round(start + index * step, 3) for index in range(count + 1)]


if __name__ == "__main__":
    result = calibrate()
    p = result.params
    print(f"L0={p.p_init} T={p.p_learn} S={p.p_slip} G={p.p_guess} margin={result.margin:.3f}")
    for name, value in result.margins.items():
        print(f"  {name}: {value:+.3f}")
    defaults = constraint_margins(BktParams())
    print(f"defaults min margin: {min(defaults.values()):.3f}")
