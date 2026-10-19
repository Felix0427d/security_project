"""Capture ChipWhisperer power traces for password-length probes."""

import argparse
import math
import os
import time

import chipwhisperer as cw
import matplotlib.pyplot as plt
import numpy as np


MIN_PASSWORD_LENGTH = 4
MAX_PASSWORD_LENGTH = 10
PROBE_CHARACTER = "x"
REFERENCE_CHARACTER = "\x01"
UART_BAUD = 9600
ADC_SAMPLES = 12000
PLOT_SAMPLES = 2500
TRACES_PER_LENGTH = 15
ANALYSIS_SAMPLES = 200
RESPONSE_TIMEOUT = 2.0
UART_IDLE_TIMEOUT_MS = 50
RESET_PULSE_SECONDS = 0.05
RESET_SETTLE_SECONDS = 0.3
RESET_DRAIN_READS = 20
PLOT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-len",
        type=int,
        default=MIN_PASSWORD_LENGTH,
        help="longueur minimale de la sonde (1-10)",
    )
    parser.add_argument(
        "--max-len",
        type=int,
        default=MAX_PASSWORD_LENGTH,
        help="longueur maximale de la sonde (1-10)",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=TRACES_PER_LENGTH,
        help="nombre de captures par longueur",
    )
    args = parser.parse_args()
    if not 1 <= args.min_len <= args.max_len <= MAX_PASSWORD_LENGTH:
        parser.error("--min-len et --max-len doivent respecter 1 <= min <= max <= 10.")
    if args.repetitions < 1:
        parser.error("--repetitions doit être supérieur ou égal à 1.")
    return args


def read_result(target) -> str:
    """Read the response and wait until the UART is idle after its next prompt."""
    chunks = []
    deadline = time.monotonic() + RESPONSE_TIMEOUT
    prompt_seen = False

    while time.monotonic() < deadline:
        timeout = UART_IDLE_TIMEOUT_MS if prompt_seen else 100
        chunk = target.read(num_char=1, timeout=timeout)
        if chunk:
            chunks.append(chunk)
            if not prompt_seen:
                response = "".join(chunks)
                for marker in ("ACCESS DENIED", "ACCESS GRANTED"):
                    result_position = response.find(marker)
                    if result_position < 0:
                        continue
                    prompt_position = response.find(
                        "Enter password:",
                        result_position + len(marker),
                    )
                    if prompt_position >= 0:
                        prompt_seen = True
                        break
        elif prompt_seen:
            return "".join(chunks)

    response = "".join(chunks)
    if response:
        received = f"Donnees recues mais reponse incomplete: {response!r}"
    else:
        received = "Aucune donnee UART recue."
    raise TimeoutError(
        "Aucune reponse complete de l'Arduino; verifie l'UART TIO1/TIO2 "
        f"et le debit de 9600 bauds. {received}"
    )


def reset_and_sync_target(scope, target) -> None:
    scope.io.nrst = 0
    time.sleep(RESET_PULSE_SECONDS)
    scope.io.nrst = None
    time.sleep(RESET_SETTLE_SECONDS)

    for _ in range(RESET_DRAIN_READS):
        if not target.read(num_char=1, timeout=100):
            break
    target.flush()


def capture_probe(scope, target, guess: str) -> tuple[np.ndarray, str]:
    reset_and_sync_target(scope, target)
    scope.arm()
    target.write(guess + "\n")

    if scope.capture():
        pending_uart = target.read(timeout=100)
        uart_detail = (
            f"Donnees UART recues: {pending_uart!r}."
            if pending_uart
            else "Aucune donnee UART recue apres l'envoi."
        )
        raise TimeoutError(
            "Aucun trigger detecte sur TIO4 (pin 14); verifie la connexion "
            f"de la sortie trigger de l'Arduino. {uart_detail}"
        )

    trace = scope.get_last_trace()
    if trace is None:
        raise RuntimeError("La capture a termine sans fournir de trace.")
    trace = np.asarray(trace)
    if trace.size != ADC_SAMPLES:
        raise RuntimeError(
            f"Trace de taille inattendue: {trace.size} au lieu de {ADC_SAMPLES}."
        )

    response = read_result(target)
    return trace, response


def print_trace_stats(label: str, trace: np.ndarray) -> None:
    window = trace[:PLOT_SAMPLES]
    peak_index = int(np.argmax(np.abs(window)))
    peak_value = float(window[peak_index])
    print(
        f"  {label} [0:{len(window)}]: "
        f"min={float(window.min()):+.6f}, "
        f"max={float(window.max()):+.6f}, "
        f"moyenne={float(window.mean()):+.6f}, "
        f"ecart-type={float(window.std()):.6f}, "
        f"RMS={float(np.sqrt(np.mean(np.square(window)))):.6f}, "
        f"crete-a-crete={float(np.ptp(window)):.6f}, "
        f"pic absolu={abs(peak_value):.6f} a l'echantillon {peak_index}"
    )


def collect_traces(
    scope, target, min_length: int, max_length: int, repetitions: int
) -> tuple[dict[int, list[np.ndarray]], dict[int, list[np.ndarray]]]:
    traces: dict[int, list[np.ndarray]] = {}
    reference_traces: dict[int, list[np.ndarray]] = {}

    for length in range(min_length, max_length + 1):
        traces[length] = []
        reference_traces[length] = []
        guess = PROBE_CHARACTER * length
        reference_guess = REFERENCE_CHARACTER * length
        for repetition in range(1, repetitions + 1):
            trace, response = capture_probe(scope, target, guess)
            traces[length].append(trace)
            result = "accepted" if "ACCESS GRANTED" in response else "denied"
            print(
                f"Longueur {length:2d}, capture {repetition}/{repetitions}: "
                f"sonde={guess!r}, {result}, {trace.size} echantillons"
            )
            print_trace_stats("Trace sonde", trace)

            reference_trace, reference_response = capture_probe(
                scope, target, reference_guess
            )
            reference_traces[length].append(reference_trace)
            reference_result = (
                "accepted" if "ACCESS GRANTED" in reference_response else "denied"
            )
            print(
                f"Longueur {length:2d}, capture {repetition}/{repetitions}: "
                f"reference={reference_guess!r}, {reference_result}, "
                f"{reference_trace.size} echantillons"
            )
            print_trace_stats("Trace reference", reference_trace)

    return traces, reference_traces


def mean_traces(traces: dict[int, list[np.ndarray]]) -> dict[int, np.ndarray]:
    return {
        length: np.mean(np.stack(waves, axis=0), axis=0)
        for length, waves in traces.items()
    }


def analyze_lengths(mean_traces: dict[int, np.ndarray]):
    """Classe les longueurs avec le score d'ecart de password_first."""
    lengths = sorted(mean_traces)
    if not lengths:
        raise RuntimeError("Aucune trace moyenne disponible pour l'analyse.")

    matrix = np.vstack([mean_traces[length] for length in lengths])
    window_end = min(matrix.shape[1], ANALYSIS_SAMPLES)
    if window_end == 0:
        raise RuntimeError("Les traces ne contiennent aucun echantillon.")

    trigger_window = matrix[:, :window_end]
    mean_power = trigger_window.mean(axis=0)
    deviations = trigger_window - mean_power
    spread = np.max(np.abs(deviations), axis=0)
    scores = np.mean(np.abs(deviations), axis=1)
    order = np.argsort(scores)[::-1]
    return lengths, matrix, deviations, spread, window_end, scores, order


def plot_zoom(traces: dict[int, list[np.ndarray]], means: dict[int, np.ndarray]):
    lengths = sorted(traces)
    sample_count = min(
        PLOT_SAMPLES,
        min(trace.size for waves in traces.values() for trace in waves),
    )
    samples = np.arange(sample_count)
    figure, axes = plt.subplots(
        len(lengths),
        1,
        figsize=(12, max(4, 1.8 * len(lengths))),
        sharex=True,
    )
    axes = np.atleast_1d(axes)

    for axis, length in zip(axes, lengths):
        for trace in traces[length]:
            axis.plot(
                samples,
                trace[:sample_count],
                color="tab:blue",
                alpha=0.25,
                linewidth=0.6,
            )
        axis.plot(
            samples,
            means[length][:sample_count],
            color="black",
            linewidth=1.3,
            label=f"Longueur {length} (moyenne)",
        )
        axis.set_ylabel(f"L={length}")
        axis.legend(loc="upper right")

    axes[-1].set_xlabel("Echantillon apres le trigger")
    figure.suptitle("Traces de puissance par longueur de sonde")
    figure.tight_layout()
    figure.savefig(os.path.join(PLOT_DIR, "password_length_zoom.png"), dpi=140)


def plot_adjacent_comparisons(means: dict[int, np.ndarray]):
    lengths = sorted(means)
    pairs = list(zip(lengths, lengths[1:]))
    if not pairs:
        return

    columns = 3
    rows = math.ceil(len(pairs) / columns)
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(15, 3.2 * rows),
        sharex=True,
    )
    axes = np.atleast_1d(axes).ravel()
    sample_count = min(PLOT_SAMPLES, min(trace.size for trace in means.values()))
    samples = np.arange(sample_count)
    plotted_traces = [trace[:sample_count] for trace in means.values()]
    shift = 1.2 * (
        max(float(trace.max()) for trace in plotted_traces)
        - min(float(trace.min()) for trace in plotted_traces)
    )

    for axis, (first, second) in zip(axes, pairs):
        axis.plot(samples, means[first][:sample_count], label=f"L={first}")
        axis.plot(
            samples,
            means[second][:sample_count] - shift,
            label=f"L={second} (decalee)",
        )
        axis.set_title(f"Longueur {first} vs {second}")
        axis.set_xlabel("Echantillon")
        axis.legend()

    for axis in axes[len(pairs) :]:
        axis.set_visible(False)

    figure.suptitle("Comparaison des traces de longueurs adjacentes")
    figure.tight_layout()
    figure.savefig(
        os.path.join(PLOT_DIR, "password_length_comparisons.png"),
        dpi=140,
    )


def plot_length_analysis(
    means: dict[int, np.ndarray],
    reference_means: dict[int, np.ndarray],
    lengths: list[int],
    deviations: np.ndarray,
    spread: np.ndarray,
    window_end: int,
    scores: np.ndarray,
    order: np.ndarray,
):
    if not lengths:
        return

    sample_count = min(
        PLOT_SAMPLES,
        min(
            min(trace.size for trace in means.values()),
            min(trace.size for trace in reference_means.values()),
        ),
    )
    samples = np.arange(sample_count)
    colors = plt.get_cmap("Spectral", len(lengths))
    figure, (trace_axis, spread_axis, score_axis) = plt.subplots(
        3, 1, figsize=(14, 11), sharex=False
    )

    for index, length in enumerate(lengths):
        trace = means[length][:sample_count]
        reference_trace = reference_means[length][:sample_count]
        color = colors(index)
        trace_axis.plot(
            samples,
            trace,
            color=color,
            alpha=0.65,
            linewidth=0.8,
            label=f"Sonde L={length}",
        )
        trace_axis.plot(
            samples,
            reference_trace,
            color=color,
            linestyle="--",
            alpha=0.85,
            linewidth=0.8,
            label=f"Reference L={length}",
        )
        spread_axis.plot(
            np.arange(window_end),
            np.abs(deviations[index]),
            color=color,
            alpha=0.65,
            linewidth=0.8,
            label=f"L={length}",
        )

    spread_axis.plot(
        np.arange(window_end),
        spread,
        color="black",
        linewidth=1.5,
        label="Dispersion maximale",
    )
    spread_axis.set_title(
        f"Ecart absolu a la moyenne des longueurs (0:{window_end})"
    )
    spread_axis.set_ylabel("|ecart| puissance")
    spread_axis.set_xlabel("Echantillon apres le trigger")
    spread_axis.legend(loc="upper right", ncol=2)

    bar_colors = [colors(index) for index in range(len(lengths))]
    bar_colors[order[0]] = "crimson"
    score_axis.bar(lengths, scores, color=bar_colors)
    score_axis.set_ylabel("Ecart absolu moyen")
    score_axis.set_xlabel("Longueur de la sonde")
    score_axis.set_title(
        f"Classement sur les {window_end} premiers echantillons "
        f"(score maximal: L={lengths[order[0]]})"
    )

    trace_axis.set_title(
        "Traces moyennes par longueur (solide=sonde, pointille=reference)"
    )
    trace_axis.set_ylabel("Amplitude")
    trace_axis.set_xlabel("Echantillon apres le trigger")
    trace_axis.legend(loc="upper right", ncol=2)
    figure.tight_layout()
    figure.savefig(
        os.path.join(PLOT_DIR, "password_length_analysis.png"),
        dpi=140,
    )
    figure.savefig(os.path.join(PLOT_DIR, "password_length_scores.png"), dpi=140)


def main():
    args = parse_args()
    scope = None
    target = None

    try:
        scope = cw.scope()
        scope.default_setup()
        scope.adc.samples = ADC_SAMPLES
        scope.io.tio1 = "serial_rx"
        scope.io.tio2 = "serial_tx"
        scope.io.tio4 = "high_z"

        target = cw.target(scope)
        target.baud = UART_BAUD
        target.flush()

        print(
            f"Sondes '{PROBE_CHARACTER}' de {args.min_len} a {args.max_len} "
            f"caracteres, {args.repetitions} capture(s) par longueur "
            "(avec reference invalide fixe)."
        )
        traces, reference_traces = collect_traces(
            scope,
            target,
            args.min_len,
            args.max_len,
            args.repetitions,
        )
    finally:
        if target is not None:
            target.dis()
        if scope is not None:
            scope.dis()
        print("Deconnecte.")

    means = mean_traces(traces)
    reference_means = mean_traces(reference_traces)
    (
        lengths,
        _,
        deviations,
        spread,
        window_end,
        scores,
        order,
    ) = analyze_lengths(means)

    print(
        f"\nAnalyse identique a password_first sur les {window_end} premiers "
        "echantillons apres le trigger."
    )
    print("Classement des longueurs par ecart absolu moyen :")
    for index in order:
        print(f"  longueur {lengths[index]} : {scores[index]:.6f}")

    print(f"\nStatistiques des traces moyennes (0:{PLOT_SAMPLES}):")
    for length in sorted(means):
        print_trace_stats(f"Longueur {length}, moyenne", means[length])
        print_trace_stats(
            f"Longueur {length}, moyenne reference", reference_means[length]
        )
    plot_length_analysis(
        means,
        reference_means,
        lengths,
        deviations,
        spread,
        window_end,
        scores,
        order,
    )
    plot_zoom(traces, means)
    plot_adjacent_comparisons(means)
    print(f"Graphes enregistres dans : {PLOT_DIR}")
    plt.show()


if __name__ == "__main__":
    main()