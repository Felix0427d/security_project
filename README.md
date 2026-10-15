# Security project

## A. Project's objectives
The goal of this project is to find a secret and password, both hashed, contained in an Arduino firmware. 

As materials, we got :
- Arduino UNO board
- ChipWhisper card (used to perform side channel attacks and fault injections during the labs)
- A .elf file we had to flash into the arduino
- Our good old computer
  
Options are quiet wide, but taking into account that we mostly worked on hardware attacks during the labs, we can therefore deduce that this way of proceeding should be prefered.

## B. Before it gets serious
First thingh I've done while going through this project, was the easy way. Trying to find the source code with the .elf file that was given as starting point. First I tried via a website, which gave me the strings but couldn't find the entire code. But our good old mister Claude foun'd a way to traduce the .elf into the source code (.cpp) super fastly. 

Fore sure this wasn't a good idea in terms of surprise when cracking this case, but as I couldn't resist, let's not be blind, this may (for sure) had inroduce in my way to see the project, a certain bias. That's why, a small mention of this is important.

-> Let's pretend this didn't happend
-> The source code Claude gave me can be found on the Repo. (Version of the code retreived by Claude Sonnet 5.5)

## C. First steps into the project

### 1. Pulse view
First, as an hardware attack check, I wanted to check if there was any communications on several pins while reseting the arduino. To do this, I used the PulseView software, and the conclusion was that on the pin 11, there was a comunication at reset time. The most probable hypothesis was an UART communication with pin 11 as TX. 

<img width="1262" height="706" alt="image" src="https://github.com/user-attachments/assets/755f29d8-795b-4c4e-987b-f6b2639547fe" />

On the image above we can see the trame send by pin 11.

### 2. Finding the RX pin

By using another arduino UNO, I interfaced the serial into UART serial. This made me able to indentify which pin was the RX one. When I cabled the TX pin of the interface Arduino into the Pin 10 of the arduino we wanted to crack. The RX led was blincking when trying to send messages. This was a nice gift from th arduino, as this could comfirm the hypothesis of an UART connection on pin 10(RX) and 11(TX). 

The way I proceed in both cases was an "essai erreur" with every pins on the board. 
I could also have worked with a simple converter but I don't have this at home so I used an Arduino.

-> Not really intresting but the arduino file of the interface can be found on the repo in the arduino_interface folder.

The trigger Pin (13). Was also founnd using PulseView, and analysing the response when we were talking with the arduino while tring codes.

### 3. Baud Rate calculation

We now want to determine the baud rate for a clean communication. Fisrt, we had to make a schematic and to take out of the arduino uno board the micro controller. We had two things in mind by doing this:

    -> The first one, make a power analysis with the ChipWhisperer 
    -> The second one, is to adapt the voltage from 3.3V (chipwhisperer) to 5V (arduino)
    
<img width="532" height="298" alt="image" src="https://github.com/user-attachments/assets/290e9fe6-fe85-4764-9055-e8a527f4906c" />

(The cabling is adapted to the real trigger, RX, and TX pins)

We also had to desolder the measure pin link between the ChipWhisperer and it's target. And put the target in high Ipedance mode, too avoid perturbing the measurements. (the python script I used to put the target in high impedance can be found on the high_imp folder)

Using the code content in baud_rate, we figured out that the baud rate is 9600, which is logical if we take a look at the source code.


## D. Power analysis 



### 1. For password lenght

After hours spent trying to find the lenght of the password and still getting the same results. I figured out that maybe the lenght doesn't matters, and the arduino only looks at the first carachters. Which was a good intuition (or maybe a logical thing after 4 hours) This phase can be passed, because not necessary. But the code and results can be found on the folder password_lenght.

### 2. For the password characters

### 3. Deeper analysis of the graphs

## F. The Secret
### 1. Before decryption
### 2. How to decrypt it
## G. Conclusion
