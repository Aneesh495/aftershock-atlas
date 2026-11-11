# Training and replay

`make fit` constructs four chronological annual lags for six outcomes. The country hash rule assigns held-out regions before normalization. Training years end in 2015; validation ends in 2018; test years are 2019-2024. Masks retain missing outcomes. No 2020 value enters a 2019 feature vector.

`network.py` computes masked Gaussian likelihood gradients through the shared tanh layer. Finite-difference tests check every parameter of a small network. Adam updates both parameters and moment states. Atomic checkpoints preserve initialized parameters, best parameters, sampler RNG and epoch. Validation chooses stopping; test scores never drive training.

`verification.py` independently reconstructs features from the frozen upstream annual panel and recomputes normalization. It loads parameter arrays directly, evaluates the frozen probe rows and compares means and spreads with recorded predictions. It also recomputes proper scores from every test record. It never calls training or regenerates missing predictions.

The failed-replay negative control changes a saved output weight, recomputes ordinary hashes and invokes the verifier as a subprocess. Correct rejection must mention saved-model replay, not an unrelated source mismatch.
