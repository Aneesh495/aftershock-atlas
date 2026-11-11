"""Original masked temporal multi-outcome network with resumable Adam state."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .io import atomic_path, canonical, write_json


class TemporalNetwork:
    def __init__(self, inputs: int, outcomes: int, seed: int, hidden: int = 48):
        if not 1 <= inputs <= 256 or not 1 <= outcomes <= 32 or not 1 <= hidden <= 256:
            raise ValueError("Network exceeds declared dimensions")
        self.inputs, self.outcomes, self.hidden, self.seed = inputs, outcomes, hidden, seed
        self.rng = np.random.default_rng(seed)
        self.params = {"w1": self.rng.normal(0, 1 / np.sqrt(inputs), (inputs, hidden)),
                       "b1": np.zeros(hidden),
                       "w2": self.rng.normal(0, .1 / np.sqrt(hidden), (hidden, 2 * outcomes)),
                       "b2": np.zeros(2 * outcomes)}
        self.m = {k: np.zeros_like(v) for k, v in self.params.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.params.items()}
        self.steps = 0
        self.epoch = 0

    def forward(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or x.shape[1] != self.inputs or not np.isfinite(x).all():
            raise ValueError("Invalid network feature matrix")
        hidden = np.tanh(x @ self.params["w1"] + self.params["b1"])
        out = hidden @ self.params["w2"] + self.params["b2"]
        return out[:, :self.outcomes], np.exp(.5 * np.clip(out[:, self.outcomes:], -6, 3))

    def objective(self, x, y, mask, weights, penalty: float = 1e-4) -> tuple[float, dict]:
        hidden = np.tanh(x @ self.params["w1"] + self.params["b1"])
        out = hidden @ self.params["w2"] + self.params["b2"]
        mean, raw = out[:, :self.outcomes], out[:, self.outcomes:]
        logvar = np.clip(raw, -6, 3)
        precision = np.exp(-logvar)
        weight = mask.astype(float) * weights[:, None]
        normalizer = max(float(weight.sum()), 1)
        weight /= normalizer
        error = mean - y
        loss = float(np.sum(weight * (.5 * logvar + .5 * error ** 2 * precision)))
        dmean = weight * error * precision
        dvar = .5 * weight * (1 - error ** 2 * precision) * ((raw > -6) & (raw < 3))
        dout = np.concatenate([dmean, dvar], axis=1)
        dh = (dout @ self.params["w2"].T) * (1 - hidden ** 2)
        gradients = {"w2": hidden.T @ dout, "b2": dout.sum(axis=0),
                     "w1": x.T @ dh, "b1": dh.sum(axis=0)}
        for name in ("w1", "w2"):
            loss += .5 * penalty * float(np.sum(self.params[name] ** 2))
            gradients[name] += penalty * self.params[name]
        if not np.isfinite(loss) or not all(np.isfinite(g).all() for g in gradients.values()):
            raise FloatingPointError("Nonfinite loss or gradient")
        return loss, gradients

    def step(self, gradients: dict, learning_rate: float = .003, clip: float = 5) -> float:
        norm = float(sum(np.sum(g ** 2) for g in gradients.values()) ** .5)
        scale = min(1, clip / max(norm, 1e-12))
        self.steps += 1
        for key, grad in gradients.items():
            grad = grad * scale
            self.m[key] = .9 * self.m[key] + .1 * grad
            self.v[key] = .999 * self.v[key] + .001 * grad ** 2
            mh = self.m[key] / (1 - .9 ** self.steps)
            vh = self.v[key] / (1 - .999 ** self.steps)
            self.params[key] -= learning_rate * mh / (np.sqrt(vh) + 1e-8)
        return norm

    def save(self, path: Path, extra: dict | None = None) -> None:
        state = {"inputs": self.inputs, "outcomes": self.outcomes, "hidden": self.hidden, "seed": self.seed,
                 "steps": self.steps, "epoch": self.epoch, "rng": self.rng.bit_generator.state, "extra": extra or {}}
        arrays = {f"{group}_{key}": value for group, values in (("p", self.params), ("m", self.m), ("v", self.v))
                  for key, value in values.items()}
        arrays["state"] = np.frombuffer(canonical(state), dtype=np.uint8)
        with atomic_path(path) as temporary:
            with temporary.open("wb") as stream:
                np.savez_compressed(stream, **arrays)

    @classmethod
    def load(cls, path: Path) -> tuple[TemporalNetwork, dict]:
        import json
        if path.stat().st_size > 20_000_000:
            raise ValueError("Oversized checkpoint")
        with np.load(path, allow_pickle=False) as saved:
            state = json.loads(saved["state"].tobytes())
            model = cls(state["inputs"], state["outcomes"], state["seed"], state["hidden"])
            for group, target in (("p", model.params), ("m", model.m), ("v", model.v)):
                for key, template in target.items():
                    array = saved[f"{group}_{key}"]
                    if array.shape != template.shape or not np.isfinite(array).all():
                        raise ValueError("Checkpoint shape or numeric corruption")
                    target[key] = array.copy()
            model.steps, model.epoch = state["steps"], state["epoch"]
            model.rng.bit_generator.state = state["rng"]
        return model, state["extra"]


def train(model: TemporalNetwork, x, y, mask, weights, validation: tuple, directory: Path,
          identity: dict, epochs: int = 300, patience: int = 40) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    checkpoint, best_path = directory / "resume.npz", directory / "best.npz"
    history_path = directory / "history.json"
    history, best, stale = [], float("inf"), 0
    initial = {k: v.copy() for k, v in model.params.items()}
    if checkpoint.exists():
        model, saved = TemporalNetwork.load(checkpoint)
        if saved["identity"] != identity:
            raise ValueError("Refuse resume across data or protocol identity")
        best, stale, history = saved["best"], saved["stale"], saved["history"]
        initial = {k: v.copy() for k, v in TemporalNetwork.load(directory / "initial.npz")[0].params.items()}
    else:
        model.save(directory / "initial.npz", {"identity": identity})
    vx, vy, vm = validation
    for epoch in range(model.epoch, epochs):
        order = model.rng.permutation(len(x))
        losses, norms = [], []
        for start in range(0, len(x), 256):
            batch = order[start:start + 256]
            loss, gradients = model.objective(x[batch], y[batch], mask[batch], weights[batch])
            norms.append(model.step(gradients))
            losses.append(loss)
        validation_loss, _ = model.objective(vx, vy, vm, np.ones(len(vx)))
        model.epoch = epoch + 1
        history.append({"epoch": model.epoch, "train_loss": float(np.mean(losses)),
                        "validation_loss": validation_loss, "gradient_norm": float(np.mean(norms))})
        if validation_loss < best - 1e-7:
            best, stale = validation_loss, 0
            model.save(best_path, {"identity": identity, "validation_loss": best})
        else:
            stale += 1
        if model.epoch % 25 == 0 or stale >= patience or model.epoch == epochs:
            model.save(checkpoint, {"identity": identity, "best": best, "stale": stale, "history": history})
            write_json(history_path, history)
        if stale >= patience:
            break
    best_model, _ = TemporalNetwork.load(best_path)
    movement = float(sum(np.sum((best_model.params[k] - v) ** 2) for k, v in initial.items()) ** .5)
    if movement <= 1e-8 or best_model.steps == 0 or not history:
        raise ValueError("No actual training occurred")
    result = {"seed": model.seed, "completed_epochs": model.epoch, "best_epoch": best_model.epoch,
              "parameter_l2_change": movement, "best_validation_loss": best,
              "optimizer_steps": model.steps, "history": history,
              "stopped": "validation_patience" if stale >= patience else "max_epochs"}
    write_json(directory / "training.json", result)
    return result
