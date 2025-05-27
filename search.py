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
    politeness_window = 6
    site_links = []
    visited_links = []
    inverted_index = {}
    # get response from home page of website
    prefix = "https://quotes.toscrape.com"
    webpage_response = requests.get("https://quotes.toscrape.com/")

    webpage = webpage_response.content
    # parse the webpage for all links
    soup = BeautifulSoup(webpage, "html.parser")
    webpage_links = soup.find_all("a")
    for link in webpage_links:
        if link.get("href").startswith("/"):
            site_links.append(prefix + link["href"])

    while site_links:
        site_link = site_links.pop(0)
        if site_link not in visited_links:  # Only visit if not already visited
            print(f"Crawling: {site_link}")
            try:
                webpage_response = requests.get(site_link)
                webpage = webpage_response.content
                soup = BeautifulSoup(webpage, "html.parser")
                
                containers = soup.find_all(class_="container")
                all_text = containers[0].get_text(separator=' ', strip=True)
                tokens = word_tokenizer(all_text)
                # add words to inverted index
                for index, token in enumerate(tokens):
                    if token not in inverted_index:
                        inverted_index[token] = {}
                        inverted_index[token][site_link] = []
                        inverted_index[token][site_link].append(index)
                    else:
                        if site_link not in inverted_index[token]:
                            inverted_index[token][site_link] = []
                            inverted_index[token][site_link].append(index)
                        else:
                            inverted_index[token][site_link].append(index)
                # parse all links which have not been visited
                webpage_links = soup.find_all("a")
                for link in webpage_links:
                    if link.get("href").startswith("/"):
                        page_link = prefix + link["href"]
                        if (page_link not in visited_links) and (page_link not in site_links):
                            site_links.append(page_link)
                visited_links.append(site_link)
            except Exception as e:
                print(e)
            # politeness window before sending next request
            time.sleep(politeness_window)
    # save inverted index to json file
    filename = 'inverted_index.json'
    with open(filename, 'w', encoding='utf-8') as file:
        json.dump(inverted_index, file, ensure_ascii=False, indent=4)
        print("Inverted index built and saved successfully!")
    

def load_index():
    filename = 'inverted_index.json'
    # load json file
    with open(filename, 'r', encoding='utf-8') as file:
        inverted_index = json.load(file)
    print("Inverted index loaded successfully!")
    return inverted_index

def print_index(inverted_index, word):
    word = word.lower()
    if word in inverted_index:
        print(inverted_index[word])
    else:
        print(f"{word} is not in inverted index!")

def power_set(lst):
    # Start with just the empty set
    result = [[]]
    # For each element in the original list
    for element in lst:
        # For each subset already in the result
        new_subsets = []
        for subset in result:
            # Create a new subset by adding the current element to it
            new_subset = subset + [element]
            new_subsets.append(new_subset)

        # Add the new subsets to the result
        result.extend(new_subsets)
    result = result[::-1]
    return result[:-1]

def find_query(inverted_index, words):
    words = " ".join(words)
    tokens = word_tokenizer(words)
    tokens_list = power_set(tokens)
    
        

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