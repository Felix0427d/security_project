
## Template de réponses orales
# 1. If we wanted to cipher the serial communication, what scheme would you recommand?
Premièrement pourquoi on veut chiffrer ? Parce que là tout ce qui se passe sur le canal UART est lisible par littéralement tout le monde... Ce qui nous as d'ailleurs permis de trouver le mot de passe. Avec chiffrement on aurait d'abord du se battre pour retrouver la clé avant de commencer quoi que ce soit de +.
On a vu en cours surtout le chiffrement par blocs et SPN (AES) et RSA. Mais ces deux méthodes sont assez lourdes et coté arduino + ATMEGA c'est pas top niveau rendement.

-> On devrait donc se diriger vers un chiffrement plutôt sur du chiffrement léger, style ASCON. Tout en gardant un chiffrement qui garde confidentialité et authenticité. (tag d'authenticité)

-> Si pas authentique, on peux modifier le flux d'info.

Mais comment ca marche ? C'est basé sur SPN -> Substitution-Permutation Network, comme aes, mais pas par bloc

Note claude : AES est un chiffrement par blocs (blocs de 128 bits, clé de 128/192/256 bits) construit sur un réseau substitution-permutation (SubBytes, ShiftRows, MixColumns, AddRoundKey). On l’utilise ensuite dans un mode (CTR, GCM...) pour faire de l’AEAD. AEAD c'est un chiffrement qui garde confidentialité.
ASCON repose sur une permutation de 320 bits (pas de chiffrement par blocs) utilisée dans une construction sponge/duplex : on « absorbe » les données associées et le message dans l’état, on « essore » le chiffré et le tag. Pas de schéma de clés étendu, la clé est simplement injectée dans l’état.

# 2. Say the firmware was signed, would you have acted differently?
Un firmware signé, c’est un firmware accompagné d’une signature numérique produite par le fabricant avec sa clé privée. L’appareil vérifie cette signature avant d’accepter ou d’exécuter le code.
Fonctionnement : 

-> Le fabricant calcule un hash du firmware (SHA-256, par exemple), puis le signe avec sa clé privée (ECDSA, Ed25519, RSA...).

-> La signature est livrée avec le firmware, dans le code quoi en gros.

-> L’appareil contient la clé publique du fabricant (en ROM ou dans une zone protégée). Il recalcule le hash du firmware reçu et vérifie la signature avec cette clé publique.

-> Si la vérification échoue, le firmware est rejeté.

-> En gros c'est pour qu'on ne change pas le firmware si on y a pas le droit (modifier ou nouveau).

-> Dans notre cas, on s'en tape parce que on ne modifie rien et on injecte rien, on observe juste. Pour fault injection ca aurait pu changer. Il aurait refusé de s'executer. Les contremesures que je propose restent les memes. Mais pour fault pas besoin de contre mesure a priori ?

# 3. Could you have used a clock glitching attack (which is not available on the CW-Nano)?

Oui
-> Principe : le cours classe le glitch d'horloge ou de tension parmi les fault injections. On provoque une erreur au bon moment pour contourner une sécurité (exemple du cours : CLKSCREW, qui contourne une vérification de signature).

Cible dans mon projet : la comparaison du mot de passe. Un glitch au moment du test pourrait le faire sauter ou mal l'évaluer, et donner ACCESS GRANTED sans connaître le mot de passe.

-> Ce dont j'ai déjà besoin : un repère temporel. J'ai le trigger sur la LED (broche 13), allumée pendant la vérification. Cela correspond à la logique du cours : l'identification (trouver l'instant) est coûteuse, l'exploitation (le glitch) est reproductible.

-> Avantage : le résultat est direct (accès accordé ou non), sans statistique sur des trace bruité comme dans monanalyse.

-> Difficulte : trouver la bonne fenêtre (décalage, largeur) par balayage. Beaucoup d'essais échouent ou provoquent des réinitialisations. Il faut aussi pouvoir injecter sur l'horloge de l'ATmega328P, qui vient du quartz externe. Mon matériel ne le permet pas, donc je ne peux pas affirmer que cela marcherait.

# 4. How would a white-box system have changed your approach?

Un système white-box est un système dont on connaît le code et le fonctionnement interne. 

-> C'est exactement ce que j'avais ! En ayant donné le firmware a une IA, qui me l'as traduite en code C++, j'avais tout. J'ai fait abstraction de cela, mais dans le fond je ne devais pas chercher 3heures les différentes pins. Ma phase d'identification à été beaucoup plus rapide bien que j'avais envie de quand même tester toute les étapes.

-> Si j'avais eu à 100% du whitebox, sans même essayer, ma phase d'identification n'aurait quasi pas existé, j'aurais juste du bien faire les branchements.
