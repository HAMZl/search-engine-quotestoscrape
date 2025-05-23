import requests
from bs4 import BeautifulSoup
import time
import json
import re

# list of stopwords
stop_words = ["it's", 'there', 'don', 'just', 'here', 'm', 'same', 'such', 'in', 'whom', 'once', 'my', 'does', 'me', 'doing', 'and', 'than', 'out', 'during', 'is', 'any', 'these', 'of', 'o', "needn't", "you'll", 'they', 'on', 'll', "doesn't", "she's", 'above', 'that', 'how', 'themselves', 'we', 'her', 'was', 'had', 'then', 'do', 'what', 'he', 'couldn', 'other', 'you', 'between', 'below', 'most', 'too', 'isn', 'down', "shan't", 'hers', 'i', "couldn't", 'won', 'only', 'mustn', 'weren', 'yourselves', 'own', 'needn', 'his', 'their', 'both', 'for', 'were', 'after', 'yours', 'but', 'will', "should've", 'your', 'because', 'before', "isn't", 'mightn', 'ourselves', 'with', 'yourself', 'has', 'hadn', 'did', 'which', 'wasn', 'ain', 'are', "wasn't", 'if', 'who', 'now', "you're", 'its', 'some', 'off', 'our', 'at', 'didn', 'aren', 'very', 'again', 'ma', 'the', 'himself', 'this', 'be', "hadn't", 'hasn', "hasn't", 'herself', "weren't", 'to', 'where', 'more', 'doesn', 'from', 'haven', "won't", 'into', 'through', 'been', 'theirs', 'them', 'should', 'until', 't', 'so', 'against', 're', 'have', 'a', "you've", "haven't", 'few', "that'll", 'over', 'why', 'it', 'shan', 'when', 'y', 'nor', "you'd", 'further', 'itself', 'not', 'those', 'having', 'under', 'd', 's', 'can', 'an', "wouldn't", 'ours', 'am', "aren't", "don't", 've', 'myself', 'each', 'wouldn', "mustn't", 'all', 'as', 'by', "mightn't", 'while', 'shouldn', 'him', 'up', "shouldn't", 'she', 'or', 'being', 'no', "didn't", 'about']


def word_tokenizer(text):
    # regex to get all tokens of words
    tokens = re.findall(r'\b\w+\b', text)
    # Remove stopwords and punctuation
    tokens = [word.lower() for word in tokens if word.isalpha() and word not in stop_words]
    return tokens

def build_index():
    pass
    

def load_index():
    pass

def print_index(inverted_index, word):
    pass


def power_set(lst):
    pass

def find_query(inverted_index, words):
    pass
        

if __name__ == "__main__":
    while True:
        # prompt user for input
        print("**Arguments: build, load, print, find:")
        
        input_string = input(">> ")
        input_list = input_string.split()
        argument = input_list[0]
        # resolve user provided argument to predefined functions
        if argument == "build":
            build_index()
        elif argument == "load":
            inverted_index = load_index()
        elif argument == "print":
            print_index(inverted_index, input_list[1])
        elif argument == "find":
            find_query(inverted_index, input_list[1:])
        elif argument == "exit":
            exit(0)
        else:
            print("Invalid argument provided!")
            exit(0)