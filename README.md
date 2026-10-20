# Security project

## A. Project's objectives
The goal of this project is to find a secret and password, both hashed, contained in an Arduino firmware. 

As materials, we got :
- Arduino UNO board
- ChipWhisper card (used to perform side channel attacks and fault injections during the labs)
- A .elf file we had to flash into the arduino
- Our good old computer
- Resistors, capacitors,and cables
  
Options are quiet wide, but taking into account that we mostly worked on hardware attacks during the labs, we can therefore deduce that this way of proceeding should be prefered.

## B. Before it gets serious
First thingh I've done while going through this project, was the easy way. Trying to find the source code with the .elf file that was given as starting point. First I tried via a website, which gave me the strings but couldn't find the entire code. But our good old mister Claude (Claude Sonnet 5.5) foun'd a way to traduce the .elf into the source code (.cpp) super fastly. 

Fore sure this wasn't a good idea in terms of surprise when trying to find the secret, but as I couldn't resist, let's not be blind, this may (for sure) had inroduce in my way to see the project, a certain bias. That's why, a small mention of this is important.

-> Let's pretend this didn't happend
-> The source code Claude gave me can be found on the Repo. (Version of the code retreived by Claude Sonnet 5.5)

## C. First steps into the project

### 1. Pulse view
First, as an hardware attack check, I wanted to check if there was any communications on several pins while reseting the arduino. To do this, I used the PulseView software, and the conclusion was that on the pin 11, there was a comunication at reset time. The most probable hypothesis was an UART communication with pin 11 as TX. 

<img width="1262" height="706" alt="image" src="https://github.com/user-attachments/assets/755f29d8-795b-4c4e-987b-f6b2639547fe" />

On the image above we can see the packet send by pin 11.

### 2. Finding the RX pin

By using another arduino UNO, I interfaced the serial into UART serial. This made me able to indentify which pin was the RX one. When I cabled the TX pin of the interface Arduino into the Pin 10 of the arduino we wanted to crack. The RX led was blincking when trying to send messages. This was a nice gift from the arduino, as this could comfirm the hypothesis of an UART connection on pin 10(RX) and 11(TX). 

The way I proceed in both cases was an "essai erreur" with every pins on the board. 
I could also have worked with a simple converter but I don't have this at home so I used an Arduino.

-> Not really intresting but the arduino file of the interface can be found on the repo in the arduino_interface folder.

The trigger Pin (13). Was also founnd using PulseView, and analysing the response when we were talking with the arduino while trying codes on the input of the terminal (during the first communications).


### 3. The real cabling adapted

To perform power analysis. We need to access the power consumption of the board. We need to put the probe of the chipwhisperer between the numerical alimentation and ground. Without forgetting to put a resistor that will serve as a shunt. 

    ATMEGA side (microcontroller on the arduino PCB):

    -> Reset pin (pin 1), connected to the reset pin of the PCB
    -> As we deduced before, the UART pins on the PCB where pin 10 and 11. Those pins corresponds to the pins 16 and 17 on the ATMEGA.
    -> The trigger pins also changes : pin number 13 on the PCB corresponds to pin 19 on the ATMEGA.
    -> We measure the tension at the entrance on pin 7.
    -> Pin 9 and 10 are linked to the external clock of the PCB

    Chipwhisperer side :

    -> On the probe pin, we connect to pin 7 of the arduino
    -> Ground and VCC connected to the breadboard. Common ground with the arduino. But tension divider between the two VCC
    -> TIO1 AND TIO2 used as UART
    -> TIO4 used as inout trigger pin

    ARDUINO PCB side :

    -> Connection of the Ground and VCC to the breadboard
    -> Connection of the reset button (pin reset)
    -> On pin 19 of the PCB we connect the trigger, to visalize on the led the messages exanges.
    -> Pin 9 and 10 are linked to the external clock of the PCB

 -> End cabling :
 
<img width="512" height="251" alt="Capture d&#39;écran 2026-10-20 094128" src="https://github.com/user-attachments/assets/c6afab4f-b491-481b-a6ce-8fbb65ad4b58" />


NB : We also had to desolder the measure pin link between the ChipWhisperer and it's target. And put the target in high Ipedance mode, too avoid perturbing the measurements. (the python script I used to put the target in high impedance can be found on the high_imp folder)


### 4. Baud Rate calculation

We now want to determine the baud rate for a clean communication. 

Using the code content in baud_rate, we figured out that the baud rate is 9600, which is logical if we take a look at the source code.


## D. Power analysis 

### 1. For password lenght

After hours spent trying to find the lenght of the password and still getting the same results. I figured out that maybe the lenght doesn't matters, and the arduino only looks at the first carachters. Which was a good intuition (or maybe a logical thing after 4 hours) This phase can be passed, because not necessary. But the code and results can be found on the folder password_lenght. We can therefore see that as we get always close but different results, what we get only depends on the noise.

### 2. For the password characters

This stage combines three signals: the trigger, the power measurement, and
the UART response. They have different roles: the trigger gives a timing
reference, the power trace reflects activity inside the microcontroller, and
the UART response reports the firmware's decision.

At the physical level, a microcontroller does not consume exactly the same
current during every instruction. In CMOS logic, transistors draw dynamic
current as internal capacitances are charged and discharged. A simplified
model is

`P_dynamic ≈ α · C · V² · f`

where `α` represents switching activity, `C` the effective capacitance, `V`
the supply voltage, and `f` the clock frequency. The measured voltage across
the current-sense path therefore changes with the processor's activity. It
also contains unrelated contributions from other instructions, peripherals,
the clock, and measurement noise; it is not a direct reading of the password
or of a single instruction.

Consequently, different guesses can make the processor follow different instruction paths
and perform different amounts of work. If a guess matches a longer prefix,
the comparison can proceed further before it exits. Those small execution
differences may change the power trace. The trigger helps compare traces from
a consistent point in time, but it does not itself reveal which character is
correct.

The script in `password_find/password_first.py` tests printable ASCII
characters from `!` to `~`, averaging 15 captures per candidate. The
sequential search in `password_find/password_full.py` starts from the
presumed prefix `f` and uses up to 30 captures per candidate. Averaging can
reduce random variation, but it cannot remove all noise or make a trace
unique to a character. The power score is therefore a way to rank candidates,
not proof of a match. The UART response `ACCESS GRANTED` confirms that the
complete candidate is correct.

### 3. Deeper analysis of the graphs

The first plot overlays the candidate traces after aligning them on the
trigger. Physically, each curve is a time-varying measurement related to the
target's current consumption; its peaks and dips reflect switching activity
as well as noise. The traces are not expected to look like a clean digital
code: many operations happen close together, and unrelated activity
contributes to the same measurement.

![Candidate power traces aligned on the trigger](password_find/password_trigger_power_traces.png)

Sample 0 corresponds to the trigger edge. The grey curves show each
candidate's averaged trace; the red curve is `f`, and the blue curve is the
highest-scoring candidate. Their substantial overlap is a reminder that
small physical differences are difficult to distinguish from noise by eye.

![Candidate score comparison](password_find/password_trigger_power_scores.png)

To summarize those curves, the script calculates each candidate's mean
absolute deviation from the average trace across candidates, over the first
200 samples after the trigger. A large score means that a candidate's
averaged trace differs more from the group in this window. It does not
directly measure how many password characters matched, nor does it establish
that the difference was caused by the comparison rather than by residual
variation.

The position-by-position plots show this limitation in the sequential
search. At the final position, the power score ranks `9` above `w`, but the
target's UART response confirms `w`. This is a useful example of the
difference between a physical side-channel observation and a confirmed
firmware result: the power trace suggests candidates, while the UART
acceptance message settles the decision.

![Final-position candidate scores](password_find/password_full_plots/position_08_scores.png)

Overall, the measurement is an indirect and noisy consequence of switching
activity inside the processor. Trigger alignment makes comparisons more
meaningful, and averaging reduces some random variation, but neither
technique turns the power score into a direct measurement of the secret. In
this experiment, power analysis guides the search; the target's UART response
confirms the result.

## F. The Secret
### 1. Before decryption
### 2. How to decrypt it
## G. Conclusion
