"""Train and evaluate sentence generation GAN using the Toronto Book Corpus."""

from sacred import Experiment
import os
from cic.models.sgan import SentenceGenerationGAN, GaussianRandomDataset
from cic.datasets.latent_ae import LatentDataset
from cic.datasets.book_corpus import TorontoBookCorpus
from cic.datasets.text_dataset import convert_numpy_array_to_strings
from cic.models.gm_autoencoder import AutoEncoder
from arcadian.dataset import MergeDataset
import cic.config
import pickle

ex = Experiment('sentence_gan')

@ex.config
def config():
    print('Running config')
    code_size = 50
    rnn_size = 600
    regenerate_latent_ukwac = False
    max_number_of_sentences = 2000000
    num_gen_layers = 40
    num_dsc_layers = 40
    sentence_gan_save_dir = os.path.join(cic.config.DATA_DIR, 'sentence_gan')
    num_epochs = 5
    restore = True  # restore sentence GAN from checkpoint
    gen_learning_rate = 0.0001
    dsc_learning_rate = 0.0001
    max_len = 20
    keep_prob = 1.0
    num_dsc_trains = 10  # number of times to train discriminator for every train of the generator

@ex.automain
def main(code_size, regenerate_latent_ukwac, max_number_of_sentences, num_gen_layers, num_dsc_layers,
         sentence_gan_save_dir, num_epochs, restore, gen_learning_rate,
         dsc_learning_rate, keep_prob, max_len, num_dsc_trains, rnn_size):
    print('Running program')

    # If we will reconstruct latent dataset, construct ukwac dataset and encoder portion of pretrained autoencoder.
    ds = None
    encoder = None

    print('Constructing UK Wac dataset')
    # ds = UKWacDataset(cic.config.UKWAC_PATH, result_save_path=cic.config.UKWAC_RESULT_PATH,
    #                      max_length=10, regenerate=False, max_number_of_sentences=max_number_of_sentences)

    ds = TorontoBookCorpus(20, result_path=cic.config.BOOK_CORPUS_RESULT,
                            min_length=5, max_num_s=max_number_of_sentences, keep_unk_sentences=False,
                            vocab_min_freq=5, vocab=None, regenerate=False)


    print('Length of UK Wac dataset: %s' % len(ds))

    if regenerate_latent_ukwac:
        print('Will regenerate latent UK Wac')
        print('Constructing pre-trained autoencoder')
        encoder = AutoEncoder(len(ds.vocab), save_dir=cic.config.GM_AE_SAVE_DIR,
                              restore=True, max_len=max_len, rnn_size=code_size,
                              encoder=True, decoder=False)

    # Build latent ukwac dataset, either by regenerating it or loading from saved results.
    print('Constructing latent UK Wac dataset')
    latent_ukwac = LatentDataset(os.path.join(cic.config.DATA_DIR, 'latent_ukwac'), code_size,
                                 data=ds, autoencoder=encoder, regenerate=regenerate_latent_ukwac)

    z_dataset = GaussianRandomDataset(len(latent_ukwac), code_size, 'z')

    merge_dataset = MergeDataset([latent_ukwac, z_dataset])

    print('Length of Latent UK Wac dataset: %s' % len(latent_ukwac))

    # Construct SentenceGAN.
    print('Constructing Sentence GAN')

    gan = SentenceGenerationGAN(code_size=code_size, num_gen_layers=num_gen_layers,
                                num_dsc_layers=num_dsc_layers,
                                num_dsc_trains=num_dsc_trains,
                                save_dir=sentence_gan_save_dir, tensorboard_name='sentence_gan',
                                restore=restore)

    # Train SentenceGAN.
    if num_epochs > 0:
        gan.train(merge_dataset, params={'gen_learning_rate': gen_learning_rate,
                                                 'dsc_learning_rate': dsc_learning_rate}, num_epochs=num_epochs)

    # Generate and print 100 examples!
    z_examples = GaussianRandomDataset(100, code_size, 'z')
    generated_codes = {'code': gan.predict(z_examples, outputs=['code'])}

    # generated_codes = DatasetPtr(latent_ukwac, range(100))

    assert len(generated_codes['code']) == 100

    print('Constructing autoencoder')

    # Create decoder to convert latent sentences back to English
    decoder = AutoEncoder(len(ds.vocab), save_dir=cic.config.GM_AE_SAVE_DIR,
                          restore=True, max_len=max_len, rnn_size=rnn_size,
                          enc_size=code_size,
                          encoder=False, decoder=True)

    print('Generating sentences')

    generated_np_sentences = decoder.predict(generated_codes, outputs=['train_prediction'])

    assert generated_np_sentences.shape == (len(generated_codes['code']), decoder.max_len)

    reversed_vocab = {ds.vocab[k]:k for k in ds.vocab}

    generated_sentences = convert_numpy_array_to_strings(generated_np_sentences, reversed_vocab,
                                            ds.stop_token,
                                            keep_stop_token=False)


    #generated_sentences = ds.convert_numpy_to_strings(generated_np_sentences)

    for each_sentence in generated_sentences:
        print(each_sentence)

    pickle.dump(generated_sentences, open(os.path.join(cic.config.DATA_DIR, 'gan_messages.pkl'), 'wb'))
