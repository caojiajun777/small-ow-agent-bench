from collections import Counter

def is_anagram(a, b):
    clean = lambda text: Counter(text.lower().split())
    return Counter(ch.lower() for ch in a if not ch.isspace()) == Counter(ch.lower() for ch in b if not ch.isspace())
