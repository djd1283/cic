"""Script to train and evaluate GAN for conversation."""
from sacred import Experiment
from cic.datasets.cornell_movie_conversation import CornellMovieConversationDataset
from cic.datasets.latent_ae import LatentDataset
from cic.datasets.text_dataset import convert_numpy_array_to_strings
from cic.models.rnet_gan import ResNetGAN
from cic.models.seq_to_seq import Seq2Seq
import numpy as np
import cic.paths as paths
from arcadian.dataset import DictionaryDataset, MergeDataset
from cic.models.rnet_gan import GaussianRandomDataset
import os

ex = Experiment('convo_gan')

@ex.config
def config():
    max_s_len = 10
    emb_size = 200  # size of word embeddings (learned)
    rnn_size = 200  # size of LSTM cell state autoencoder
    rand_size = 100 # size of random vector input to gan

    max_vocab_len = 10000
    regen_cmd = False
    regen_l_cmd = False  # regenerate latent cornell movie dialogues

    restore = False  # restore convo gan from checkpoint
    restore_ae = False  # restore autoencoder from checkpoint

    ae_save_dir = os.path.join(paths.DATA_DIR, 'cmd_ae/')  # where to save data
    l_message_save_dir = os.path.join(paths.DATA_DIR, 'latent_messages/')  # where to save message vectors
    l_response_save_dir = os.path.join(paths.DATA_DIR, 'latent_responses/')  # where to save response vectors
    gan_save_dir = os.path.join(paths.DATA_DIR, 'convo_gan/')  # where to save convo gan model parameters
    cornell_dir = os.path.join(paths.DATA_DIR, 'cornell_convos/')  # where to save cornell movie dialogues data

    n_epochs = 100  # number of epochs to train convo gan
    n_ae_epochs = 50  # number of epochs to train autoencoder
    n_dsc_layers = 20  # number of resnet layers in discriminator
    n_gen_layers = 20  # number of resnet layers in generator
    gen_lr = 0.0001  # generator learning rate
    dsc_lr = 0.0001  # discriminator learning rate
    n_dsc_trains = 5  # number of discriminator trains per generator train
    t_v_split = 0.9  # split total dataset into train and validation sets

@ex.automain
def main(max_s_len, emb_size, rnn_size, cornell_dir, max_vocab_len, regen_cmd, n_ae_epochs, ae_save_dir,
         l_message_save_dir, regen_l_cmd, rand_size, n_dsc_layers, n_gen_layers, n_dsc_trains, gan_save_dir,
         n_epochs, t_v_split, l_response_save_dir, restore_ae, restore, gen_lr, dsc_lr):

    """Game Plan: Train an autoencoder to produce sentence representations for each message
    and each response in the Cornell Movie Dialogues dataset. Train GAN to take message vector as input
    and output response vector."""

    # Create CMD dataset
    cmd = CornellMovieConversationDataset(max_s_len, reverse_inputs=False, seed='seed',
                                         save_dir=cornell_dir, max_vocab_len=max_vocab_len,
                                         regenerate=regen_cmd)

    messages = DictionaryDataset({'message': cmd.messages})
    responses = DictionaryDataset({'message': cmd.responses})

    # Train autoencoder on all messages and responses
    sents = np.concatenate([cmd.messages, cmd.responses], axis=0)
    sent_ds = {'message': sents, 'response': sents.copy()}  # autoencoder has same input and output
    ae = Seq2Seq(max_s_len, len(cmd.vocab), emb_size, rnn_size, save_dir=ae_save_dir, restore=restore_ae)
    ae.train(sent_ds, num_epochs=n_ae_epochs)

    # Create latent dataset
    l_messages = LatentDataset(save_dir=l_message_save_dir, latent_size=rnn_size, data=messages, autoencoder=ae,
                          regenerate=regen_l_cmd, feature_name='context')
    l_responses = LatentDataset(save_dir=l_response_save_dir, latent_size=rnn_size, data=responses, autoencoder=ae,
                          regenerate=regen_l_cmd, feature_name='data')

    # Create random inputs and combine message codes with z codes
    rand_zs = GaussianRandomDataset(len(l_messages), rand_size, 'z')

    # l_messages and rand_zs have same feature name, concatenate features
    # Test! We have model output its input
    examples = MergeDataset([l_messages, rand_zs, {'data': l_messages.dataset}])

    t_examples, v_examples = examples.split(t_v_split, seed='seed')

    # Construct convo GAN
    convo_gan = ResNetGAN(rand_size, n_gen_layers, n_dsc_layers, n_dsc_trains, rnn_size,
                          context_size=rnn_size, save_dir=gan_save_dir, restore=restore)

    # Train
    convo_gan.train(t_examples, num_epochs=n_epochs, params={'dsc_lr': dsc_lr, 'gen_lr': gen_lr})

    # Evaluate - generate responses to input messages
    codes = convo_gan.predict(v_examples, outputs=['outputs'])
    np_responses = ae.generate_responses_from_codes(codes, n=1)

    responses = convert_numpy_array_to_strings(np_responses, cmd.inverse_vocab,
                                              cmd.stop_token, keep_stop_token=False)

    # Print generated responses
    for index in range(len(responses)):
        print('Message: %s' % (' '.join(cmd.examples[v_examples.indices[index]][0])))
        print('Response: %s' % responses[index])


