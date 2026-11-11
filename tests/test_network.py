import numpy as np
import pytest

from aftershock.network import TemporalNetwork


def test_all_gradients_against_finite_differences():
    model = TemporalNetwork(3, 2, 11, 4)
    x = np.array([[1, -1, 0], [.2, .4, -.5]])
    y = np.array([[.2, .5], [1, 0]])
    mask = np.array([[True, True], [True, False]])
    w = np.array([1, 2])
    loss, gradients = model.objective(x, y, mask, w)
    for key, parameter in model.params.items():
        for index in np.ndindex(parameter.shape):
            old = parameter[index]
            parameter[index] = old + 1e-5
            hi = model.objective(x, y, mask, w)[0]
            parameter[index] = old - 1e-5
            lo = model.objective(x, y, mask, w)[0]
            parameter[index] = old
            assert gradients[key][index] == pytest.approx((hi - lo) / 2e-5, abs=2e-8)


def test_checkpoint_replays_optimizer_and_rng(tmp_path):
    model = TemporalNetwork(2, 1, 29, 4)
    x = np.ones((8, 2))
    y = np.ones((8, 1))
    mask = y.astype(bool)
    model.step(model.objective(x, y, mask, np.ones(8))[1])
    model.save(tmp_path / "saved.npz", {"data": "known"})
    restored, extra = TemporalNetwork.load(tmp_path / "saved.npz")
    assert extra == {"data": "known"}
    assert np.array_equal(model.forward(x)[0], restored.forward(x)[0])
    assert model.rng.permutation(10).tolist() == restored.rng.permutation(10).tolist()
    for obj in (model, restored):
        obj.step(obj.objective(x, y, mask, np.ones(8))[1])
    assert np.array_equal(model.params["w1"], restored.params["w1"])
