"""Interactive line-oriented UART terminal for the external Arduino."""

import msvcrt
import sys

import chipwhisperer as cw


UART_BAUD = 9600
UART_READ_TIMEOUT_MS = 20


def main() -> None:
    scope = None
    target = None
    line: list[str] = []

    try:
        scope = cw.scope()
        scope.default_setup()
        scope.io.tio1 = "serial_rx"
        scope.io.tio2 = "serial_tx"
        scope.io.tio4 = "high_z"

        target = cw.target(scope)
        target.baud = UART_BAUD

        print(
            f"Terminal UART actif a {UART_BAUD} bauds. "
            "Entree envoie la ligne; Ctrl+C ferme la connexion."
        )
        while True:
            received = target.read(num_char=1, timeout=UART_READ_TIMEOUT_MS)
            if received:
                sys.stdout.write(received)
                sys.stdout.flush()

            while msvcrt.kbhit():
                character = msvcrt.getwch()
                if character in ("\x00", "\xe0"):
                    msvcrt.getwch()
                elif character in ("\r", "\n"):
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    target.write("".join(line) + "\n")
                    line.clear()
                elif character == "\b":
                    if line:
                        line.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                else:
                    line.append(character)
                    sys.stdout.write(character)
                    sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nFermeture du terminal UART.")
    finally:
        if target is not None:
            target.dis()
        if scope is not None:
            scope.dis()
        print("Deconnecte.")


if __name__ == "__main__":
    main()
