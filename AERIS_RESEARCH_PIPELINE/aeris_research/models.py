from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .common import PipelineError


@dataclass(frozen=True)
class PODModel:
    mean: np.ndarray
    basis: np.ndarray
    singular_values: np.ndarray

    @classmethod
    def fit(cls, fields: np.ndarray) -> "PODModel":
        values = np.asarray(fields, dtype=np.float64)
        if values.ndim != 2 or values.shape[0] < 2:
            raise PipelineError("POD requires at least two field snapshots")
        if not np.all(np.isfinite(values)):
            raise PipelineError("POD input contains non-finite values")
        mean = values.mean(axis=0)
        _, singular_values, right = np.linalg.svd(values - mean, full_matrices=False)
        return cls(mean=mean, basis=right, singular_values=singular_values)

    @property
    def max_rank(self) -> int:
        return self.basis.shape[0]

    def encode(self, fields: np.ndarray, rank: int | None = None) -> np.ndarray:
        use_rank = self.max_rank if rank is None else min(int(rank), self.max_rank)
        return (np.asarray(fields) - self.mean) @ self.basis[:use_rank].T

    def decode(self, coefficients: np.ndarray, rank: int | None = None) -> np.ndarray:
        values = np.asarray(coefficients)
        use_rank = values.shape[-1] if rank is None else min(int(rank), values.shape[-1])
        return self.mean + values[..., :use_rank] @ self.basis[:use_rank]

    def explained_variance_ratio(self) -> np.ndarray:
        variance = self.singular_values**2
        total = variance.sum()
        return variance / total if total else np.zeros_like(variance)


@dataclass(frozen=True)
class RidgeModel:
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    weights: np.ndarray

    @classmethod
    def fit(cls, features: np.ndarray, targets: np.ndarray, alpha: float = 1.0e-6) -> "RidgeModel":
        x = np.asarray(features, dtype=np.float64)
        y = np.asarray(targets, dtype=np.float64)
        if x.ndim != 2 or y.ndim != 2 or x.shape[0] != y.shape[0]:
            raise PipelineError("ridge inputs must be aligned two-dimensional arrays")
        mean = x.mean(axis=0)
        scale = x.std(axis=0)
        scale[scale < 1.0e-12] = 1.0
        normalised = (x - mean) / scale
        augmented = np.column_stack([np.ones(x.shape[0]), normalised])
        penalty = np.eye(augmented.shape[1]) * alpha
        penalty[0, 0] = 0.0
        weights = np.linalg.solve(augmented.T @ augmented + penalty, augmented.T @ y)
        return cls(mean, scale, weights)

    def predict(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float64)
        normalised = (x - self.feature_mean) / self.feature_scale
        return np.column_stack([np.ones(x.shape[0]), normalised]) @ self.weights


class DenseAutoencoder:
    """Small deterministic nonlinear field encoder-decoder trained with Adam.

    The model is deliberately dependency-light: a tanh encoder maps the full
    cell field to a regularised latent vector and a linear decoder maps back to
    the field. Training and any latent regressor must use geometry-disjoint
    splits supplied by the caller.
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int,
        *,
        seed: int = 42,
        latent_penalty: float = 1.0e-4,
        weight_decay: float = 1.0e-6,
    ):
        if input_dim < 1 or latent_dim < 1:
            raise ValueError("autoencoder dimensions must be positive")
        rng = np.random.default_rng(seed)
        bound = np.sqrt(6.0 / (input_dim + latent_dim))
        self.encoder_weight = rng.uniform(-bound, bound, size=(input_dim, latent_dim))
        self.encoder_bias = np.zeros(latent_dim)
        self.decoder_weight = self.encoder_weight.T.copy()
        self.decoder_bias = np.zeros(input_dim)
        self.field_mean = np.zeros(input_dim)
        self.field_scale = 1.0
        self.latent_penalty = float(latent_penalty)
        self.weight_decay = float(weight_decay)

    def _normalise(self, fields: np.ndarray) -> np.ndarray:
        return (np.asarray(fields, dtype=np.float64) - self.field_mean) / self.field_scale

    def encode(self, fields: np.ndarray) -> np.ndarray:
        values = self._normalise(fields)
        return np.tanh(values @ self.encoder_weight + self.encoder_bias)

    def decode(self, latent: np.ndarray) -> np.ndarray:
        reconstructed = np.asarray(latent) @ self.decoder_weight + self.decoder_bias
        return reconstructed * self.field_scale + self.field_mean

    def reconstruct(self, fields: np.ndarray) -> np.ndarray:
        return self.decode(self.encode(fields))

    def fit(
        self,
        train: np.ndarray,
        validation: np.ndarray | None = None,
        *,
        epochs: int = 250,
        learning_rate: float = 3.0e-3,
        patience: int = 40,
    ) -> list[dict[str, float]]:
        values = np.asarray(train, dtype=np.float64)
        if values.ndim != 2 or values.shape[0] < 2:
            raise PipelineError("autoencoder requires at least two training snapshots")
        if not np.all(np.isfinite(values)):
            raise PipelineError("autoencoder input contains non-finite values")
        self.field_mean = values.mean(axis=0)
        centred = values - self.field_mean
        self.field_scale = float(np.sqrt(np.mean(centred**2)))
        if self.field_scale < 1.0e-12:
            self.field_scale = 1.0
        x = self._normalise(values)
        x_validation = self._normalise(validation) if validation is not None else None

        parameters = [
            self.encoder_weight,
            self.encoder_bias,
            self.decoder_weight,
            self.decoder_bias,
        ]
        first_moments = [np.zeros_like(parameter) for parameter in parameters]
        second_moments = [np.zeros_like(parameter) for parameter in parameters]
        beta1, beta2, epsilon = 0.9, 0.999, 1.0e-8
        best = [parameter.copy() for parameter in parameters]
        best_loss = float("inf")
        stale = 0
        history = []

        for epoch in range(1, int(epochs) + 1):
            latent = np.tanh(x @ self.encoder_weight + self.encoder_bias)
            predicted = latent @ self.decoder_weight + self.decoder_bias
            residual = predicted - x
            reconstruction_loss = float(np.mean(residual**2))
            latent_loss = float(self.latent_penalty * np.mean(latent**2))
            regularisation = float(
                self.weight_decay
                * (np.mean(self.encoder_weight**2) + np.mean(self.decoder_weight**2))
            )
            gradient_predicted = 2.0 * residual / residual.size
            gradient_decoder_weight = latent.T @ gradient_predicted
            gradient_decoder_weight += (
                2.0 * self.weight_decay * self.decoder_weight / self.decoder_weight.size
            )
            gradient_decoder_bias = gradient_predicted.sum(axis=0)
            gradient_latent = gradient_predicted @ self.decoder_weight.T
            gradient_latent += 2.0 * self.latent_penalty * latent / latent.size
            gradient_activation = gradient_latent * (1.0 - latent**2)
            gradient_encoder_weight = x.T @ gradient_activation
            gradient_encoder_weight += (
                2.0 * self.weight_decay * self.encoder_weight / self.encoder_weight.size
            )
            gradient_encoder_bias = gradient_activation.sum(axis=0)
            gradients = [
                gradient_encoder_weight,
                gradient_encoder_bias,
                gradient_decoder_weight,
                gradient_decoder_bias,
            ]

            for index, (parameter, gradient) in enumerate(zip(parameters, gradients, strict=True)):
                first_moments[index] = beta1 * first_moments[index] + (1.0 - beta1) * gradient
                second_moments[index] = beta2 * second_moments[index] + (1.0 - beta2) * gradient**2
                corrected_first = first_moments[index] / (1.0 - beta1**epoch)
                corrected_second = second_moments[index] / (1.0 - beta2**epoch)
                parameter -= learning_rate * corrected_first / (np.sqrt(corrected_second) + epsilon)

            validation_loss = float("nan")
            if x_validation is not None:
                z_validation = np.tanh(x_validation @ self.encoder_weight + self.encoder_bias)
                validation_prediction = z_validation @ self.decoder_weight + self.decoder_bias
                validation_loss = float(np.mean((validation_prediction - x_validation) ** 2))
                monitored = validation_loss
            else:
                monitored = reconstruction_loss
            history.append(
                {
                    "epoch": float(epoch),
                    "train_loss": reconstruction_loss + latent_loss + regularisation,
                    "train_reconstruction_loss": reconstruction_loss,
                    "validation_reconstruction_loss": validation_loss,
                }
            )
            if monitored < best_loss - 1.0e-10:
                best_loss = monitored
                best = [parameter.copy() for parameter in parameters]
                stale = 0
            else:
                stale += 1
            if stale >= patience:
                break

        for parameter, best_value in zip(parameters, best, strict=True):
            parameter[...] = best_value
        return history

    def save(self, path: Path) -> None:
        with Path(path).open("wb") as stream:
            np.savez_compressed(
                stream,
                model_type="regularized_tanh_autoencoder",
                encoder_weight=self.encoder_weight,
                encoder_bias=self.encoder_bias,
                decoder_weight=self.decoder_weight,
                decoder_bias=self.decoder_bias,
                field_mean=self.field_mean,
                field_scale=np.asarray(self.field_scale),
                latent_penalty=np.asarray(self.latent_penalty),
                weight_decay=np.asarray(self.weight_decay),
            )


def grouped_geometry_split(geometry_groups: np.ndarray, *, seed: int = 42) -> dict[str, np.ndarray]:
    groups = np.asarray(geometry_groups).astype(str)
    unique = np.unique(groups)
    if unique.size < 3:
        raise PipelineError(
            "strict train/validation/test splitting requires at least 3 geometries; "
            f"found {unique.size}"
        )
    rng = np.random.default_rng(seed)
    shuffled = unique.copy()
    rng.shuffle(shuffled)
    number_test = max(1, int(round(0.15 * unique.size)))
    number_validation = max(1, int(round(0.15 * unique.size)))
    if number_test + number_validation >= unique.size:
        number_test = number_validation = 1
    test_groups = set(shuffled[:number_test])
    validation_groups = set(shuffled[number_test : number_test + number_validation])
    train_groups = set(shuffled[number_test + number_validation :])
    output = {
        "train": np.flatnonzero(np.isin(groups, list(train_groups))),
        "validation": np.flatnonzero(np.isin(groups, list(validation_groups))),
        "test": np.flatnonzero(np.isin(groups, list(test_groups))),
    }
    memberships = {name: set(groups[indices]) for name, indices in output.items()}
    if (
        memberships["train"] & memberships["validation"]
        or memberships["train"] & memberships["test"]
        or memberships["validation"] & memberships["test"]
    ):
        raise AssertionError("geometry leakage in grouped split")
    return output


def field_error_metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    residual = np.asarray(prediction) - np.asarray(truth)
    return {
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mae": float(np.mean(np.abs(residual))),
        "max_abs": float(np.max(np.abs(residual))),
    }
