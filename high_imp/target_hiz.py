"""Build and flash a CW-Nano firmware that leaves its active GPIOs Hi-Z."""

import argparse
import glob
import os
import shutil
import subprocess

import chipwhisperer as cw


CW_ROOT = r"C:\Users\felix\ChipWhispererSCA101\chipwhisperer"
MCU_DIR = os.path.join(CW_ROOT, "firmware", "mcu")
SOURCE_DIR = os.path.join(MCU_DIR, "simpleserial-base")
BUILD_DIR = os.path.join(MCU_DIR, "simpleserial-base-hiz")
SOURCE_FILE = "simpleserial-base.c"
HEX_FILE = os.path.join(BUILD_DIR, "simpleserial-base-CWNANO.hex")

HIZ_FUNCTION = """
static void target_gpio_hiz(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_2 | GPIO_PIN_4 | GPIO_PIN_7
             | GPIO_PIN_9 | GPIO_PIN_10;
    gpio.Mode = GPIO_MODE_ANALOG;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);
}
"""


def build_env():
    extra = []
    if shutil.which("make") is None:
        pattern = os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\ezwinports.make*\bin"
        )
        extra.extend(glob.glob(pattern))

    if shutil.which("arm-none-eabi-gcc") is None:
        for base in (
            r"C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi",
            r"C:\Program Files\Arm GNU Toolchain arm-none-eabi",
        ):
            extra.extend(glob.glob(os.path.join(base, "*", "bin")))

    if shutil.which("rm") is None:
        extra.append(r"C:\Program Files\Git\usr\bin")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(extra + [env["PATH"]])
    return env


def prepare_firmware():
    """Create a dedicated build copy; leave the installed example untouched."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    for name in ("makefile", SOURCE_FILE):
        source_path = os.path.join(SOURCE_DIR, name)
        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"Fichier source introuvable : {source_path}")
        shutil.copy2(source_path, os.path.join(BUILD_DIR, name))

    firmware_path = os.path.join(BUILD_DIR, SOURCE_FILE)
    with open(firmware_path, encoding="utf-8") as source:
        code = source.read()

    include_anchor = '#include "hal.h"\n'
    includes = (
        '#include "stm32f0xx_hal_gpio.h"\n'
        '#include "stm32f0xx_hal_rcc.h"\n'
    )
    if code.count(include_anchor) != 1:
        raise RuntimeError("Impossible de localiser l'inclusion de hal.h.")
    code = code.replace(include_anchor, include_anchor + includes, 1)

    function_anchor = "uint8_t get_key("
    if code.count(function_anchor) != 1:
        raise RuntimeError("Impossible de localiser get_key().")
    code = code.replace(function_anchor, HIZ_FUNCTION + "\n" + function_anchor, 1)

    setup_anchor = (
        "trigger_setup(); // setup trigger pin, allows trigger_high() "
        "and trigger_low() to work\n"
    )
    if code.count(setup_anchor) != 1:
        raise RuntimeError("Impossible de localiser l'initialisation du trigger.")
    code = code.replace(
        setup_anchor,
        setup_anchor
        + "\ttarget_gpio_hiz(); // Disable target GPIO outputs and internal pulls\n",
        1,
    )

    with open(firmware_path, "w", encoding="utf-8", newline="\n") as output:
        output.write(code)


def build_firmware(env):
    make = shutil.which("make", path=env["PATH"])
    if make is None:
        raise FileNotFoundError("make introuvable : installe make puis relance.")

    subprocess.run(
        [
            make,
            "PLATFORM=CWNANO",
            "CRYPTO_TARGET=NONE",
            "SS_VER=SS_VER_1_1",
        ],
        cwd=BUILD_DIR,
        env=env,
        check=True,
    )
    if not os.path.isfile(HEX_FILE):
        raise FileNotFoundError(f"Firmware compilé introuvable : {HEX_FILE}")


def flash_firmware():
    scope = None
    try:
        scope = cw.scope()
        scope.default_setup()
        cw.program_target(scope, cw.programmers.STM32FProgrammer, HEX_FILE)
        print("Firmware Hi-Z programmé sur la ChipWhisperer-Nano.")
    finally:
        if scope is not None:
            scope.dis()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="compile le firmware sans le programmer",
    )
    args = parser.parse_args()

    prepare_firmware()
    build_firmware(build_env())
    if args.build_only:
        print(f"Compilation OK : {HEX_FILE}")
    else:
        flash_firmware()


if __name__ == "__main__":
    main()
