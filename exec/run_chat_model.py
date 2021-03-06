"""Train and evaluate chat model trained on Cornell Movie Dialogues."""
import sacred
from cic.datasets.cmd_one_turn import CornellMovieConversationDataset
from cic.datasets.text_dataset import convert_numpy_array_to_strings, construct_numpy_from_messages
from arcadian.dataset import DictionaryDataset
from cic.models.seq_to_seq import Seq2Seq
import cic.paths
import os
import numpy as np

def generate_response_from_model(msg, ds, model, n, reverse_vocab):
    """Specific function to generate a single response for a single string.
    Details must be specified.

        msg - input message string
        ds - instance of CornellMovieConversationDataset
        model - instance of Seq2Seq
        n - only sample response words from n most probable words at each time-step
        reverse_vocab - mapping from indices to words"""

    msg_tk = ds.nlp.tokenizer(msg.lower())
    msg_split = [str(tk) for tk in msg_tk if str(tk) in ds.vocab]
    np_msg = construct_numpy_from_messages([msg_split], ds.vocab, model.max_s_len, unk_token='<UNK>')

    while True:
        np_response = model.generate_responses(np_msg, n=n)
        response = convert_numpy_array_to_strings(np_response, reverse_vocab,
                                                  ds.stop_token, keep_stop_token=False)[0]

        if '<UNK>' in response or response == '':
            continue
        else:
            break
    response = response.capitalize()
    response = response.replace(' .', '.')
    response = response.replace(' ,', ',')
    response = response.replace(' !', '!')
    response = response.replace(" '", "'")
    response = response.replace(' ?', '?')
    response = response.replace(' :', ':')
    response = response.replace(" n't", "n't")

    return response

if __name__ == '__main__':
    ex = sacred.Experiment('chat')

    @ex.config
    def config():
        max_s_len = 10
        emb_size = 200
        rnn_size = 200
        num_epochs = 10
        keep_prob = 0.5
        restore=False
        n = 10  # when generating response, select each word from top n most probable words

        split_frac = 0.99
        split_seed = 'seed'
        num_val_print = 50  # number of validation responses to print
        max_vocab_len = 10000
        regen = False
        attention = True

        save_dir = os.path.join(cic.paths.DATA_DIR, 'chat_model/')
        cornell_dir = os.path.join(cic.paths.DATA_DIR, 'cornell_convos/')

        talk_to_bot = False

    @ex.automain
    def main(max_s_len, emb_size, rnn_size, num_epochs, split_frac, num_val_print, regen, n, attention,
             split_seed, save_dir, restore, cornell_dir, talk_to_bot, max_vocab_len, keep_prob):
        print('Starting program')

        ds = CornellMovieConversationDataset(max_s_len, reverse_inputs=False, seed='seed',
                                             save_dir=cornell_dir, max_vocab_len=max_vocab_len,
                                             regenerate=regen)

        print('Dataset len: %s' % len(ds))
        print('Vocab len: %s' % len(ds.vocab))

        train_ds, val_ds = ds.split(split_frac, seed=split_seed)

        model = Seq2Seq(max_s_len, max_s_len, len(ds.vocab), emb_size, rnn_size,
                        attention=attention, save_dir=save_dir, restore=restore, tensorboard_name='chat')

        if num_epochs > 0:
            model.train(train_ds, num_epochs=num_epochs, params={'keep_prob': keep_prob})

        np_responses = model.generate_responses(val_ds, n=n)

        reverse_vocab = {ds.vocab[k]: k for k in ds.vocab}

        responses = convert_numpy_array_to_strings(np_responses, reverse_vocab,
                                                ds.stop_token,
                                                keep_stop_token=False)

        print()
        for index, response in enumerate(responses):

            if index >= num_val_print:
                break

            print(' '.join(ds.examples[val_ds.indices[index]][0])),
            print(' --> ' + response)


        # Talk to bot

        if talk_to_bot:
            while True:
                msg = input("You: ")

                response = generate_response_from_model(msg, ds, model, n, reverse_vocab)

                print('Bot: %s' % response)


