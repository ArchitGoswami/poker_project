#description: This program aims to build a card deck 
#generator and distributor with the purpose of  
#eventually building a poker game 

#author: Archit Goswami

from random import *

def main():

    print("This program will give you the 52 cards of a deck \n")
    numberOfPlayers = int(input("How many players? \n"))

    for n in range (1,numberOfPlayers+1):

        print("This is player ",n)
        numberOfCards = int(input("How many cards would you like to give to the current player ? \n"))
        playerCards = distributor(numberOfCards)
        print("The total cards distributed so far are: " , distributedCards)
        finalList[n]=[playerCards]
        print ("Each of the players hands are:", finalList)
        sendCardsToApp()

def distributor(numberOfCards):

    if numberOfCards > 52:
        print ("You can not distribute more cards, the deck is over")

    else:
        playerCards = []
        
        for n in range (0,numberOfCards):
            randomDigit = str(randint(1,13))
            randomSuitNumber = randint(0,3)
            randomSuit = ""
            
            if randomSuitNumber == 0:
                randomSuit = "S"
            elif randomSuitNumber == 1:
                randomSuit = "C"
            elif randomSuitNumber == 2:
                randomSuit = "H"
            else:
                randomSuit = "D"
            card = randomSuit+randomDigit

            try :
                distributedCards.index(card)
                distributor(1)

            except ValueError:                        
                print(card)
                distributedCards.append(card)
                playerCards.append(card)

        return playerCards


def sendCardsToApp():
    
    print("send cards to app here")

distributedCards = []
playerCards = []
finalList = {}
main()


