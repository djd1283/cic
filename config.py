"""Copyright 2017 David Donahue. Stores global paths and constants."""
import os

DATA_DIR = './data'
MS_MARCO_TRAIN_SET = os.path.join(DATA_DIR, 'ms_marco/train_v1.1.json')
SQUAD_TRAIN_SET = os.path.join(DATA_DIR, 'squad/train-v1.1.json')
BASELINE_MODEL_SAVE_DIR = os.path.join(DATA_DIR, 'baseline_models/')

# CONSTANTS
MAX_QUESTION_WORDS = 30
MAX_ANSWER_WORDS = 10
MAX_CONTEXT_WORDS = 200
SPACY_GLOVE_EMB_SIZE = 300
