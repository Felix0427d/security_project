"""Reproduce the password-first-character SPA analysis from the notebook."""

import time
from pathlib import Path

import chipwhisperer as cw
import matplotlib.pyplot as plt
import numpy as np


N_REPEAT = 5
DIAGNOSTIC_REPEAT = 5
RESET_PULSE_SECONDS = 0.05
RESET_SETTLE_SECONDS = 0.3
RESET_UART_TIMEOUT_MS = 100
PLOT_DIR = Path(__file__).resolve().parent


def resync(target, timeout: int = 400) -> None:
    """Drain pending UART data before starting a capture campaign."""
    target.ser.flush()
    while target.ser.read(200, timeout=timeout):
        pass
    target.ser.flush()


def reset_and_sync_target(scope, target) -> None:
    """Reset the target and drain its startup UART output."""
    scope.io.nrst = 0
    time.sleep(RESET_PULSE_SECONDS)
    scope.io.nrst = None
    time.sleep(RESET_SETTLE_SECONDS)
    resync(target, timeout=RESET_UART_TIMEOUT_MS)


def capture_guess(scope, target, guess: str) -> np.ndarray | None:
    """Reset, send one guess, capture the trigger interval, and drain its response."""
    reset_and_sync_target(scope, target)
    scope.arm()
    target.ser.write((guess + "\n").encode("latin-1"))
    timed_out = scope.capture()
    target.ser.read(100, timeout=120)
    if timed_out:
        return None
    return scope.get_last_trace()


def collect_candidate_traces(scope, target) -> dict[str, np.ndarray]:
    # Moyenne plusieurs captures par caractere pour reduire le bruit de mesure.
    traces = {}
    for codepoint in range(33, 127):
        character = chr(codepoint)
        captures = [
            trace
            for trace in (
                capture_guess(scope, target, character) for _ in range(N_REPEAT)
            )
            if trace is not None
        ]
        if captures:
            traces[character] = np.mean(captures, axis=0)
    return traces


def analyze_traces(traces: dict[str, np.ndarray]):
    if not traces:
        raise RuntimeError(
            "Aucune trace valide n'a ete capturee; verifiez la connexion et le trigger."
        )

    # Chaque ligne correspond a un caractere teste, chaque colonne a un echantillon.
    characters = sorted(traces)
    matrix = np.vstack([traces[character] for character in characters])

    # La dispersion entre candidats permet de reperer l'instant le plus discriminant.
    mean_power = matrix.mean(axis=0)
    deviations = matrix - mean_power
    spread = np.max(np.abs(deviations), axis=0)
    leakage_sample = int(np.argmax(spread))

    # Au point de fuite, les candidats les plus eloignes de la moyenne sont prioritaires.
    scores = np.abs(deviations[:, leakage_sample])
    order = np.argsort(scores)[::-1]
    best = characters[order[0]]

    return characters, matrix, spread, leakage_sample, scores, order, best


def save_and_show_plot(filename: str) -> None:
    path = PLOT_DIR / filename
    plt.savefig(path, dpi=140)
    print(f"Plot enregistre : {path}")
    plt.show()


def plot_results(
    traces: dict[str, np.ndarray],
    characters: list[str],
    matrix: np.ndarray,
    spread: np.ndarray,
    leakage_sample: int,
    scores: np.ndarray,
    best: str,
) -> None:
    # La premiere figure localise l'echantillon ou les candidats divergent le plus.
    plt.figure(figsize=(12, 3))
    plt.plot(spread)
    plt.axvline(
        leakage_sample,
        color="red",
        ls="--",
        label="instant de fuite @ {}".format(leakage_sample),
    )
    plt.title("Ecart max de puissance entre candidats (points de fuite SPA)")
    plt.xlabel("echantillon")
    plt.ylabel("|ecart| puissance")
    plt.legend()
    plt.tight_layout()
    save_and_show_plot("password_leakage_spread.png")

    # La deuxieme figure compare les formes d'onde autour de cet echantillon.
    a = max(0, leakage_sample - 150)
    b = min(matrix.shape[1], leakage_sample + 150)
    plt.figure(figsize=(12, 4))
    for character in characters:
        plt.plot(
            range(a, b),
            traces[character][a:b],
            color="lightgray",
            linewidth=0.4,
        )
    if "f" in traces:
        plt.plot(
            range(a, b),
            traces["f"][a:b],
            color="red",
            linewidth=1.6,
            label="'f' (indice wiki)",
        )
    plt.plot(
        range(a, b),
        traces[best][a:b],
        color="blue",
        linewidth=1.0,
        label="meilleur = {!r}".format(best),
    )
    plt.axvline(leakage_sample, color="k", ls=":")
    plt.title("Puissance de chaque caractere autour de l'instant de fuite")
    plt.xlabel("echantillon")
    plt.ylabel("puissance")
    plt.legend()
    plt.tight_layout()
    save_and_show_plot("password_candidate_traces_zoom.png")

    # La troisieme figure classe les candidats selon leur ecart au point de fuite.
    colors = ["red" if character == "f" else "steelblue" for character in characters]
    plt.figure(figsize=(14, 3))
    plt.bar(range(len(characters)), scores, color=colors)
    plt.xticks(range(len(characters)), characters, fontsize=7)
    plt.title(
        "Amplitude de fuite de puissance a l'echantillon {}  ('f' en rouge)".format(
            leakage_sample
        )
    )
    plt.ylabel("|ecart| puissance")
    plt.tight_layout()
    save_and_show_plot("password_leakage_scores.png")


def trace_moyenne(scope, target, character: str, n: int = DIAGNOSTIC_REPEAT):
    captures = [
        trace
        for trace in (capture_guess(scope, target, character) for _ in range(n))
        if trace is not None
    ]
    return np.mean(captures, axis=0) if captures else None


def plot_diagnostic(scope, target) -> None:
    # Compare le caractere suppose correct a quelques essais incorrects connus.
    false_characters = ["!", "0", "~"]
    correct_trace = trace_moyenne(scope, target, "f")
    false_traces = {
        character: trace_moyenne(scope, target, character)
        for character in false_characters
    }

    plt.figure(figsize=(12, 4))
    for character, trace in false_traces.items():
        if trace is not None:
            plt.plot(trace, linewidth=0.8, label="faux '%s'" % character)
    if correct_trace is not None:
        plt.plot(
            correct_trace,
            color="red",
            linewidth=1.6,
            label="'f' (suppose correct)",
        )
    plt.legend()
    plt.title("Diagnostic : 'f' vs caracteres faux (moyenne x20)")
    plt.xlabel("echantillon")
    plt.ylabel("puissance")
    plt.tight_layout()
    save_and_show_plot("password_diagnostic_full.png")

    plt.figure(figsize=(12, 4))
    for character, trace in false_traces.items():
        if trace is not None:
            plt.plot(
                trace[:600],
                linewidth=0.9,
                label="faux '%s'" % character,
            )
    if correct_trace is not None:
        plt.plot(
            correct_trace[:600],
            color="red",
            linewidth=1.6,
            label="'f'",
        )
    plt.legend()
    plt.title("Zoom debut de trace (600 premiers echantillons)")
    plt.xlabel("echantillon")
    plt.ylabel("puissance")
    plt.tight_layout()
    save_and_show_plot("password_diagnostic_zoom.png")

    if correct_trace is not None and false_traces.get("!") is not None:
        # Affiche l'endroit ou les deux traces de reference different le plus.
        difference = np.abs(correct_trace - false_traces["!"])
        print(
            "Divergence max a l'echantillon",
            int(np.argmax(difference)),
            "valeur",
            round(float(difference.max()), 2),
        )


def main() -> None:
    scope = None
    target = None
    try:
        # Initialise ChipWhisperer et configure la liaison serie avec la cible.
        scope = cw.scope()
        scope.default_setup()
        target = cw.target(scope, cw.targets.SimpleSerial2)
        target.baud = 9600

        print("Connecte.")
        # Verifie qu'une capture fonctionne avant de lancer toute la campagne.
        test_trace = capture_guess(scope, target, "f")
        print(
            "capture test:",
            None
            if test_trace is None
            else "OK, %d samples" % len(test_trace),
        )

        traces = collect_candidate_traces(scope, target)
        (
            characters,
            matrix,
            spread,
            leakage_sample,
            scores,
            order,
            best,
        ) = analyze_traces(traces)

        print("Instant de fuite (echantillon):", leakage_sample)
        # Affiche le classement complet des meilleurs indices de premier caractere.
        print("Top 10 par amplitude de fuite de PUISSANCE a cet instant:")
        for index in order[:10]:
            print(f"  {characters[index]!r} : {scores[index]:.4f}")
        print("\n>>> 1er caractere le plus probable (puissance):", repr(best))
        if "f" in characters:
            rank_f = list(order).index(characters.index("f")) + 1
            print(f"    ('f' est classe #{rank_f} sur {len(characters)})")

        plot_results(
            traces, characters, matrix, spread, leakage_sample, scores, best
        )
        plot_diagnostic(scope, target)
    finally:
        # Ferme les connexions meme si une capture ou l'analyse echoue.
        if target is not None:
            target.dis()
        if scope is not None:
            scope.dis()
        print("Deconnecte.")


if __name__ == "__main__":
    main()
