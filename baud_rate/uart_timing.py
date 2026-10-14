"""Estimate and decode 8N1 UART from a digital waveform exported as CSV."""

import argparse
import bisect
import csv
import statistics
import time
from dataclasses import dataclass
from pathlib import Path


UART_BAUD_CANDIDATES = (
    9600,
    4800,
    19200,
    2400,
    38400,
    57600,
    115200,
    1200,
    230400,
    600,
)


@dataclass
class Capture:
    times: list[float]
    levels: list[int]


def parse_level(value: str) -> int:
    normalized = value.strip().lower()
    if normalized in {"1", "high", "true"}:
        return 1
    if normalized in {"0", "low", "false"}:
        return 0
    raise ValueError(f"Valeur logique invalide : {value!r}")


def read_capture(path: Path, column: str | None) -> Capture:
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        sample = csv_file.read(4096)
        csv_file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error as error:
            raise ValueError("Impossible de détecter le séparateur CSV.") from error
        reader = csv.DictReader(csv_file, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("Le CSV doit contenir une ligne d'en-têtes.")

        time_column = next(
            (
                name
                for name in reader.fieldnames
                if name.strip().lower().startswith(("time", "timestamp"))
            ),
            None,
        )
        if time_column is None:
            raise ValueError(
                "Colonne de temps absente : exporte le temps en secondes "
                "(par ex. « Time [s] »)."
            )

        if column is None:
            column = next(
                (name for name in reader.fieldnames if name != time_column), None
            )
        if column not in reader.fieldnames:
            raise ValueError(f"Colonne logique introuvable : {column!r}")

        times: list[float] = []
        levels: list[int] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                timestamp = float(row[time_column])
                level = parse_level(row[column])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Ligne CSV {row_number} invalide : {error}"
                ) from error
            if times and timestamp <= times[-1]:
                raise ValueError(
                    f"Les temps doivent être strictement croissants "
                    f"(ligne {row_number})."
                )
            times.append(timestamp)
            levels.append(level)

    if len(times) < 2:
        raise ValueError("La capture doit contenir au moins deux échantillons.")
    return Capture(times, levels)


def transition_intervals(capture: Capture) -> list[float]:
    edge_times = [
        capture.times[index]
        for index in range(1, len(capture.levels))
        if capture.levels[index] != capture.levels[index - 1]
    ]
    return [
        later - earlier for earlier, later in zip(edge_times, edge_times[1:])
    ]


def estimate_baud(
    intervals: list[float],
    min_baud: int = 300,
    max_baud: int = 1_000_000,
    max_run_bits: int = 12,
) -> tuple[float, float]:
    if len(intervals) < 4:
        raise ValueError(
            "Pas assez de transitions UART pour estimer le débit "
            "(il en faut au moins cinq)."
        )
    if min_baud <= 0 or max_baud < min_baud:
        raise ValueError("Plage de baud rate invalide.")

    candidates = {
        interval / divisor
        for interval in intervals
        for divisor in range(1, max_run_bits + 1)
        if 1 / max_baud <= interval / divisor <= 1 / min_baud
    }
    best: tuple[int, float, float, float] | None = None
    for bit_period in candidates:
        errors = []
        for interval in intervals:
            bit_count = round(interval / bit_period)
            if 1 <= bit_count <= max_run_bits:
                error = abs(interval - bit_count * bit_period) / bit_period
                if error <= 0.2:
                    errors.append(error)
        if not errors:
            continue
        score = (len(errors), -statistics.median(errors), bit_period)
        if best is None or score > best[:3]:
            best = (*score, bit_period)

    if best is None:
        raise ValueError(
            "Aucune durée de bit cohérente trouvée; vérifie la capture "
            "et la plage de baud rates."
        )
    return 1 / best[3], len(
        [
            interval
            for interval in intervals
            if 1 <= round(interval / best[3]) <= max_run_bits
            and abs(interval - round(interval / best[3]) * best[3])
            / best[3]
            <= 0.2
        ]
    ) / len(intervals)


def sample_level(capture: Capture, timestamp: float) -> int | None:
    index = bisect.bisect_right(capture.times, timestamp) - 1
    if index < 0 or timestamp > capture.times[-1]:
        return None
    return capture.levels[index]


def decode_8n1(
    capture: Capture, baud: float
) -> tuple[bytes, int]:
    bit_period = 1 / baud
    starts = [
        capture.times[index]
        for index in range(1, len(capture.levels))
        if capture.levels[index - 1] == 1 and capture.levels[index] == 0
    ]
    decoded = bytearray()
    framing_errors = 0
    next_frame_time = float("-inf")

    for start in starts:
        if start < next_frame_time:
            continue
        start_sample = sample_level(capture, start + 0.5 * bit_period)
        data_samples = [
            sample_level(capture, start + (1.5 + bit) * bit_period)
            for bit in range(8)
        ]
        stop_sample = sample_level(capture, start + 9.5 * bit_period)
        if start_sample is None or None in data_samples or stop_sample is None:
            continue
        next_frame_time = start + 10 * bit_period
        if start_sample != 0 or stop_sample != 1:
            framing_errors += 1
            continue
        value = sum(int(level) << bit for bit, level in enumerate(data_samples))
        decoded.append(value)

    return bytes(decoded), framing_errors


def probe_live_uart() -> None:
    try:
        import chipwhisperer as cw
    except ImportError as error:
        raise RuntimeError(
            "Le mode direct nécessite le paquet ChipWhisperer "
            "dans cet environnement Python."
        ) from error

    scope = None
    target = None
    try:
        scope = cw.scope()
        scope.default_setup()
        scope.io.tio1 = "serial_rx"
        scope.io.tio2 = "serial_tx"
        target = cw.target(scope)
        print(
            "Recherche UART en direct : envoi d'un saut de ligne "
            "et recherche de la réponse « ACCESS DENIED »."
        )
        print(
            "Pinout CW-Nano : TIO2/pin 12 TX -> Arduino RX10; "
            "Arduino TX11 -> TIO1/pin 10 RX."
        )
        for baud in UART_BAUD_CANDIDATES:
            target.baud = baud
            target.flush()
            target.write("x\n")
            time.sleep(0.05)
            response = ""
            for _ in range(5):
                response += target.read(num_char=1, timeout=100)
                if "ACCESS DENIED" in response:
                    break
            print(f"{baud:>6} bauds : {response!r}")
            if "ACCESS DENIED" in response:
                print(f"\nBaud rate détecté : {baud} bauds (8N1)")
                return
        print(
            "\nPas de réponse reconnue. HS1/pin 4 et nRST/pin 5 ne sont pas "
            "des broches UART; utilise TIO1/pin 10 et TIO2/pin 12. "
            "Vérifie l'alimentation et la masse commune. Si le firmware Hi-Z "
            "du projet est flashé, reprogramme-le avec "
            "high_imp\\target_hiz.py --keep-uart."
        )
    finally:
        if target is not None:
            target.dis()
        if scope is not None:
            scope.dis()


def listen_live_uart(baud: int = 9600, duration: float = 5.0) -> None:
    try:
        import chipwhisperer as cw
    except ImportError as error:
        raise RuntimeError(
            "Le mode direct nécessite le paquet ChipWhisperer "
            "dans cet environnement Python."
        ) from error

    scope = None
    target = None
    try:
        scope = cw.scope()
        scope.default_setup()
        scope.io.tio1 = "serial_rx"
        scope.io.tio2 = "serial_tx"
        target = cw.target(scope)
        target.baud = baud
        target.flush()
        print(
            f"Écoute UART passive à {baud} bauds pendant {duration:g} s. "
            "Redémarre la cible maintenant."
        )

        deadline = time.monotonic() + duration
        received = ""
        while time.monotonic() < deadline:
            timeout_ms = max(1, min(200, int((deadline - time.monotonic()) * 1000)))
            received += target.read(num_char=1, timeout=timeout_ms)

        print(f"Reçu : {received!r}")
        if received:
            print(
                f"Texte : {received.encode('ascii', errors='replace').decode('ascii')}"
            )
        else:
            print("Aucun octet reçu pendant la fenêtre d'écoute.")
    finally:
        if target is not None:
            target.dis()
        if scope is not None:
            scope.dis()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sans fichier CSV, teste les baud rates courants en direct via "
            "le ChipWhisperer; avec un CSV, estime le débit depuis la forme d'onde."
        )
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        nargs="?",
        help="CSV exporté depuis PulseView (mode hors ligne)",
    )
    parser.add_argument(
        "--column", help="nom de la colonne logique (par défaut : première après le temps)"
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="écoute passivement l'UART au lieu de balayer des débits",
    )
    parser.add_argument("--baud", type=int, default=9600, help="débit du mode --listen")
    parser.add_argument("--min-baud", type=int, default=300)
    parser.add_argument("--max-baud", type=int, default=1_000_000)
    args = parser.parse_args()

    if args.listen:
        if args.csv_file is not None:
            parser.error("--listen ne s'utilise pas avec un fichier CSV.")
        listen_live_uart(args.baud)
        return

    if args.csv_file is None:
        probe_live_uart()
        return

    capture = read_capture(args.csv_file, args.column)
    intervals = transition_intervals(capture)
    baud, confidence = estimate_baud(
        intervals, min_baud=args.min_baud, max_baud=args.max_baud
    )
    payload, framing_errors = decode_8n1(capture, baud)

    print(f"Baud rate estimé : {baud:.1f} bauds")
    print(f"Transitions cohérentes : {confidence:.0%}")
    print(f"Octets 8N1 décodés : {payload.hex(' ')}")
    print(f"Texte : {payload.decode('ascii', errors='replace')!r}")
    print(f"Erreurs de stop/framing : {framing_errors}")


if __name__ == "__main__":
    main()
