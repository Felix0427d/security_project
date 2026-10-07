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

## C. First steps into the project
### 1. Pulse view
First, as an hardware attack check, I wanted to check if there was any communications on several pins while reseting the arduino. To do this, I used the PulseView software, and the conclusion was that on the pin 11, there was a comunication at reset time. The most probable hypothesis was an UART communication with pin 11 as TX. 

<img width="1262" height="706" alt="image" src="https://github.com/user-attachments/assets/755f29d8-795b-4c4e-987b-f6b2639547fe" />

On the image above we can see the trame send by pin 11.

### 2. Finding the RX pin

By using another arduino UNO, I interfaced the serial into UART serial. This made me able to indentify which pin was the RX one. When I cabled the TX pin of the interface Arduino into the Pin 10 of the arduino we wanted to crack. The RX led was blincking when trying to send messages. This was a nice gift from th arduino, as this could comfirm the hypothesis of an UART connection on pin 10(RX) and 11(TX). (Not really intresting but the arduino file of the interface can be found on the repo).

The way I proceed in both cases was an "essai erreur" with every pins on the board. 

### 3. Fisrt communication with the board

## D. Second part, timing analysis using the ChipWhisperer
## E. Third part, finding the password, and capture the secret
## F. Conclusion
