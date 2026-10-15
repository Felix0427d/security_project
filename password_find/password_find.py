"""Reproduce the password-first-character SPA analysis from the notebook."""
import time
from pathlib import Path
import chipwhisperer as cw
import matplotlib.pyplot as plt
import numpy as np

# Reglages des captures et delais necessaires au redemarrage de la cible.
N_REPEAT = 5
DIAGNOSTIC_REPEAT = 5
RESET_PULSE_SECONDS = 0.05
RESET_SETTLE_SECONDS = 0.3
RESET_UART_TIMEOUT_MS = 100
# Enregistre les figures a cote de ce script.
PLOT_DIR = Path(__file__).resolve().parent

def resync(target, timeout: int = 400) -> None:
    """Vide les donnees serie en attente avant une nouvelle capture."""
    target.ser.flush()
    # Lit jusqu'a ce qu'il n'y ait plus de donnees, afin de repartir proprement.
    while target.ser.read(200, timeout=timeout):
        pass
    target.ser.flush()

def reset_and_sync_target(scope, target) -> None:
    """Redemarre la cible puis vide son message serie de demarrage."""
    scope.io.nrst = 0
    time.sleep(RESET_PULSE_SECONDS)
    scope.io.nrst = None
    time.sleep(RESET_SETTLE_SECONDS)
    # Le redemarrage peut produire une reponse serie qui ne doit pas fausser l'essai.
    resync(target, timeout=RESET_UART_TIMEOUT_MS)

def capture_guess(scope, target, guess: str) -> np.ndarray | None:
    """Envoie un candidat, capture la trace declenchee et lit la reponse serie."""
    reset_and_sync_target(scope, target)
    # On arme avant l'envoi pour ne pas manquer le front du signal de trigger.
    scope.arm()
    target.ser.write((guess + "\n").encode("latin-1"))
    timed_out = scope.capture()
    # Vide la reponse avant l'essai suivant pour garder une tentative par capture.
    target.ser.read(100, timeout=120)
    if timed_out:
        return None
    return scope.get_last_trace()

def trace_activity(trace: np.ndarray) -> float:
    """Estime l'activite par la variation entre echantillons, pas la duree du trigger."""
    # Une trace plus variable obtient un score plus eleve sur une fenetre identique.
    return float(np.abs(np.diff(trace)).sum())

def collect_candidate_traces(
    scope, target
) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    traces = {}
    activity_scores = {}
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
            # Score chaque capture avant la moyenne pour conserver l'activite mesuree.
            activity_scores[character] = float(
                np.mean([trace_activity(trace) for trace in captures])
            )
    return traces, activity_scores

def analyze_traces(
    traces: dict[str, np.ndarray], activity_scores: dict[str, float]
):
    # Sans mesure valide, un classement aurait un resultat trompeur.
    if not traces or not activity_scores:
        raise RuntimeError(
            "Aucune trace valide n'a ete capturee; verifiez la connexion et le trigger."
        )

    # Le meilleur candidat est celui dont le score moyen d'activite est maximal.
    characters = sorted(activity_scores)
    scores = np.array([activity_scores[character] for character in characters])
    order = np.argsort(scores)[::-1]
    best = characters[order[0]]

    return characters, scores, order, best

def save_and_show_plot(filename: str) -> None:
    """Enregistre une figure puis l'affiche."""
    path = PLOT_DIR / filename
    plt.savefig(path, dpi=140)
    print(f"Plot enregistre : {path}")
    plt.show()

def plot_results(
    traces: dict[str, np.ndarray],
    characters: list[str],
    scores: np.ndarray,
    order: np.ndarray,
) -> None:
    # Le score integre classe les candidats selon l'activite mesuree sur la trace entiere.
    # Le rouge signale le caractere 'f' utilise comme point de comparaison connu.
    colors = ["red" if character == "f" else "steelblue" for character in characters]
    plt.figure(figsize=(14, 3))
    plt.bar(range(len(characters)), scores, color=colors)
    plt.xticks(range(len(characters)), characters, fontsize=7)
    plt.title(
        "Variation totale (proxy d'activite) par candidat ('f' en rouge)"
    )
    plt.xlabel("caractere candidat")
    plt.ylabel("variation totale de puissance")
    plt.tight_layout()
    save_and_show_plot("password_candidate_activity.png")

    # Compare les traces des candidats les mieux classes sur toute la fenetre capturee.
    top_characters = [characters[index] for index in order[:5]]
    # Ajoute aussi 'f' au graphique s'il ne fait pas partie des cinq premiers.
    if "f" in traces and "f" not in top_characters:
        top_characters.append("f")
    plt.figure(figsize=(12, 4))
    for character in top_characters:
        plt.plot(
            traces[character],
            linewidth=1.0,
            label="{} (score {:.2f})".format(
                repr(character), scores[characters.index(character)]
            ),
        )
    plt.title("Traces de puissance des candidats les plus actifs")
    plt.xlabel("echantillon")
    plt.ylabel("puissance")
    plt.legend()
    plt.tight_layout()
    save_and_show_plot("password_candidate_activity_traces.png")

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

        traces, activity_scores = collect_candidate_traces(scope, target)
        characters, scores, order, best = analyze_traces(traces, activity_scores)

        # Affiche les candidats classes par activite cumulee de leur trace.
        print("Top 10 par variation totale (proxy d'activite):")
        for index in order[:10]:
            print(f"  {characters[index]!r} : {scores[index]:.4f}")
        print("\n>>> 1er caractere le plus probable (activite):", repr(best))
        if "f" in characters:
            rank_f = list(order).index(characters.index("f")) + 1
            print(f"    ('f' est classe #{rank_f} sur {len(characters)})")

        plot_results(traces, characters, scores, order)
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
