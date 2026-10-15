"""Analyse les traces de puissance en les alignant sur le trigger."""
from pathlib import Path

import chipwhisperer as cw
import matplotlib.pyplot as plt
import numpy as np

# Meme nombre de repetitions que dans la cellule d'analyse du notebook.
N_REPEAT = 15
DIAGNOSTIC_REPEAT = 20
# Nombre d'echantillons analyses a partir du front du trigger (t = 0).
TRIGGER_WINDOW_SAMPLES = 200
# Enregistre les figures a cote de ce script.
PLOT_DIR = Path(__file__).resolve().parent


def resync(target, timeout: int = 400) -> None:
    """Vide les donnees serie en attente avant une campagne de captures."""
    target.ser.flush()
    # Lit jusqu'a ce qu'il n'y ait plus de donnees, afin de repartir proprement.
    while target.ser.read(200, timeout=timeout):
        pass
    target.ser.flush()


def capture_guess(scope, target, guess: str) -> np.ndarray | None:
    """Envoie un candidat, capture sa trace puis lit la reponse serie."""
    # On arme avant l'envoi pour ne pas manquer le front du signal de trigger.
    scope.arm()
    target.ser.write((guess + "\n").encode("latin-1"))
    timed_out = scope.capture()
    # Vide la reponse avant l'essai suivant pour garder une tentative par capture.
    target.ser.read(100, timeout=120)
    if timed_out:
        return None
    return scope.get_last_trace()


def collect_candidate_traces(scope, target) -> dict[str, np.ndarray]:
    """Moyenne les captures de chaque caractere, comme dans le notebook."""
    # Le notebook resynchronise une fois avant la campagne, pas avant chaque essai.
    resync(target)
    traces = {}
    # Parcourt les caracteres ASCII imprimables de '!' a '~'.
    for codepoint in range(33, 127):
        character = chr(codepoint)
        # Les captures en timeout sont ecartees; les autres sont conservees.
        captures = [
            trace
            for trace in (
                capture_guess(scope, target, character) for _ in range(N_REPEAT)
            )
            if trace is not None
        ]
        if captures:
            # La trace moyenne sert aux graphiques et reduit le bruit aleatoire.
            traces[character] = np.mean(captures, axis=0)
    return traces


def analyze_traces(traces: dict[str, np.ndarray]):
    """Compare l'activite de chaque candidat dans la fenetre suivant le trigger."""
    if not traces:
        raise RuntimeError(
            "Aucune trace valide n'a ete capturee; verifiez la connexion et le trigger."
        )

    # Chaque ligne contient la trace moyenne d'un candidat, alignee sur le trigger.
    characters = sorted(traces)
    matrix = np.vstack([traces[character] for character in characters])

    # L'echantillon 0 est le front du trigger; on limite l'analyse a la fenetre utile.
    window_end = min(matrix.shape[1], TRIGGER_WINDOW_SAMPLES)
    if window_end == 0:
        raise RuntimeError("Les traces capturees ne contiennent aucun echantillon.")
    trigger_window = matrix[:, :window_end]

    # Mesure la deviation de chaque candidat par rapport a la puissance moyenne.
    mean_power = trigger_window.mean(axis=0)
    deviations = trigger_window - mean_power
    spread = np.max(np.abs(deviations), axis=0)

    # Le score resume l'ecart moyen du candidat dans toute la fenetre apres trigger.
    scores = np.mean(np.abs(deviations), axis=1)
    order = np.argsort(scores)[::-1]
    best = characters[order[0]]

    return characters, matrix, spread, window_end, scores, order, best


def save_and_show_plot(filename: str) -> None:
    """Enregistre une figure puis l'affiche."""
    path = PLOT_DIR / filename
    plt.savefig(path, dpi=140)
    print(f"Plot enregistre : {path}")
    plt.show()

def plot_results(
    traces: dict[str, np.ndarray],
    characters: list[str],
    matrix: np.ndarray,
    spread: np.ndarray,
    window_end: int,
    scores: np.ndarray,
    best: str,
) -> None:
    # Graphique 1: montre la dispersion des mesures depuis le front du trigger.
    plt.figure(figsize=(12, 3))
    plt.plot(spread)
    plt.axvline(0, color="red", ls="--", label="front du trigger (t=0)")
    plt.title("Dispersion de puissance apres le front du trigger")
    plt.xlabel("echantillon apres le trigger")
    plt.ylabel("|ecart| puissance")
    plt.legend()
    plt.tight_layout()
    save_and_show_plot("password_trigger_power_spread.png")

    # Graphique 2: compare les mesures de puissance des candidats apres le trigger.
    start = 0
    end = window_end
    plt.figure(figsize=(12, 4))
    for character in characters:
        plt.plot(
            range(start, end),
            traces[character][start:end],
            color="lightgray",
            linewidth=0.4,
        )
    if "f" in traces:
        plt.plot(
            range(start, end),
            traces["f"][start:end],
            color="red",
            linewidth=1.6,
            label="'f' (indice wiki)",
        )
    plt.plot(
        range(start, end),
        traces[best][start:end],
        color="blue",
        linewidth=1.0,
        label="meilleur = {!r}".format(best),
    )
    plt.axvline(0, color="black", ls=":", label="front du trigger")
    plt.title("Puissance de chaque caractere apres le front du trigger")
    plt.xlabel("echantillon apres le trigger (t=0)")
    plt.ylabel("puissance")
    plt.legend()
    plt.tight_layout()
    save_and_show_plot("password_trigger_power_traces.png")

    # Graphique 3: ecart absolu moyen de chaque candidat dans la fenetre trigger.
    colors = ["red" if character == "f" else "steelblue" for character in characters]
    plt.figure(figsize=(14, 3))
    plt.bar(range(len(characters)), scores, color=colors)
    plt.xticks(range(len(characters)), characters, fontsize=7)
    plt.title(
    "Ecart absolu moyen sur les {} premiers echantillons ('f' en rouge)".format(
        window_end
        )
    )
    plt.ylabel("ecart absolu moyen de puissance")
    plt.tight_layout()
    save_and_show_plot("password_trigger_power_scores.png")


def trace_moyenne(scope, target, character: str, n: int = DIAGNOSTIC_REPEAT):
    """Capture plusieurs fois un caractere et renvoie sa trace moyenne."""
    captures = [
        trace
        for trace in (capture_guess(scope, target, character) for _ in range(n))
        if trace is not None
    ]
    # Aucun resultat valide est signale par None pour eviter de tracer une fausse courbe.
    return np.mean(captures, axis=0) if captures else None


def plot_diagnostic(scope, target) -> None:
    # Compare le caractere suppose correct a quelques essais incorrects connus.
    false_characters = ["!", "0", "~"]
    correct_trace = trace_moyenne(scope, target, "f")
    false_traces = {
        character: trace_moyenne(scope, target, character)
        for character in false_characters
    }

    # Premiere vue: comparer les traces moyennes sur toute leur longueur.
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
    plt.title(
        "Diagnostic : 'f' vs caracteres faux (moyenne x{})".format(
            DIAGNOSTIC_REPEAT
        )
    )
    plt.xlabel("echantillon")
    plt.ylabel("puissance")
    plt.tight_layout()
    save_and_show_plot("password_diagnostic_full.png")

    # Deuxieme vue: agrandir le debut, ou la comparaison du mot de passe commence.
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

        # Synchronise la liaison pour le test initial de communication.
        resync(target)
        # Une capture test permet de verifier rapidement le branchement et le trigger.
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
            window_end,
            scores,
            order,
            best,
        ) = analyze_traces(traces)

        print(
            "Fenetre d'analyse apres le trigger : echantillons "
            f"0 a {window_end - 1} (front du trigger = t=0)"
        )
        for index in order[:10]:
            print(f"  {characters[index]!r} : {scores[index]:.4f}")
        print("\n>>> 1er caractere le plus probable (puissance):", repr(best))
        if "f" in characters:
            rank_f = list(order).index(characters.index("f")) + 1
            print(f"    ('f' est classe #{rank_f} sur {len(characters)})")

        plot_results(
            traces, characters, matrix, spread, window_end, scores, best
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
