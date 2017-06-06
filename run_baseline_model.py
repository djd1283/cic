"""Trains and predicts using the baseline LSTM model."""
print('Starting program')
import tensorflow as tf
import squad_dataset_tools as sdt
import config
import baseline_model
import numpy as np
import attention

#Hyperparameters
LEARNING_RATE = .0004
NUM_PARAGRAPHS = 60 # 18000
LSTM_HIDDEN_DIM = 800
NUM_EPOCHS = 100
NUM_EXAMPLES_TO_PRINT = 20
TRAIN_FRAC = 0.8
PREDICT_PROBABILITIES = False
VALIDATE_PROPER_INPUTS = False

tf_config = tf.ConfigProto()
tf_config.graph_options.optimizer_options.global_jit_level = tf.OptimizerOptions.ON_1

print('Loading SQuAD dataset')
paragraphs = sdt.load_squad_dataset_from_file(config.SQUAD_TRAIN_SET)
if NUM_PARAGRAPHS is not None:
    paragraphs = paragraphs[:NUM_PARAGRAPHS]
print('Processing %s paragraphs...' % len(paragraphs))
print('Tokenizing paragraph samples')
tk_paragraphs = sdt.tokenize_paragraphs(paragraphs)
print('Building vocabulary')
vocab_dict = sdt.generate_vocabulary_for_paragraphs(tk_paragraphs).token2id
vocabulary = sdt.invert_dictionary(vocab_dict)  # becomes list of words essentially
vocabulary_size = len(vocab_dict)
print('Len vocabulary: %s' % vocabulary_size)
print('Flatting paragraphs into examples')
examples = sdt.convert_paragraphs_to_flat_format(tk_paragraphs)
print('Converting each example to numpy arrays')
np_questions, np_answers, np_contexts, ids, np_as \
    = sdt.generate_numpy_features_from_squad_examples(examples, vocab_dict,
                                                      answer_indices_from_context=True,
                                                      answer_is_span=True)
print('Maximum index in answers should be less than max context size + 1: %s' % np_answers.max())
num_examples = np_questions.shape[0]
print('Number of examples: %s' % np_questions.shape[0])
contexts = [example[2] for example in examples]
questions = [example[0] for example in examples]
context_lengths = []
for each_context in contexts:
    context_tokens = each_context.split()
    context_lengths.append(len(context_tokens))
print('Average context length: %s' % np.mean(context_lengths))
print('Context length deviation: %s' % np.std(context_lengths))
print('Max context length: %s' % np.max(context_lengths))
num_empty_answers = 0
for i in range(np_answers.shape[0]):
    if np.isclose(np_answers[i], np.zeros([np_answers.shape[1]])).all():
        num_empty_answers += 1
print('Fraction of empty answer vectors (should be close to zero): %s' % (num_empty_answers / num_examples))
print('Loading embeddings for each word in vocabulary')
np_embeddings = sdt.construct_embeddings_for_vocab(vocab_dict)
num_embs = np_embeddings.shape[0]
emb_size = np_embeddings.shape[1]
num_empty_embs = 0
print('Embedding shape: %s' % str(np_embeddings[0, :].shape))
for i in range(num_embs):
    if np.isclose(np_embeddings[i, :], np.zeros([emb_size])).all():
        num_empty_embs += 1
fraction_empty_embs = num_empty_embs / num_embs
print('Fraction of empty embeddings in vocabulary: %s' % fraction_empty_embs)
index_prob_size = config.MAX_CONTEXT_WORDS
num_answers_in_context = 0
for each_example in examples:
    answer = each_example[1]
    context = each_example[2]
    if answer in context:
        num_answers_in_context += 1
print('Fraction of answers found in passages: %s' % (num_answers_in_context / num_examples))

print('Loading embeddings into Tensorflow')
tf_embeddings = tf.Variable(np_embeddings, name='word_embeddings', dtype=tf.float32, trainable=False)
print('Constructing placeholders')
tf_question_indices = tf.placeholder(dtype=tf.int32, shape=(None, config.MAX_QUESTION_WORDS), name='question_indices')
tf_context_indices = tf.placeholder(dtype=tf.int32, shape=(None, config.MAX_CONTEXT_WORDS), name='context_indices')
tf_answer_indices = tf.placeholder(dtype=tf.int32, shape=(None, 2), name='answer_indices')
tf_batch_size = tf.placeholder(dtype=tf.int32, name='batch_size')

tf_question_embs = tf.nn.embedding_lookup(tf_embeddings, tf_question_indices, name='question_embeddings')
tf_context_embs = tf.nn.embedding_lookup(tf_embeddings, tf_context_indices, name='context_embeddings')
print('Question embeddings shape: %s' % str(tf_question_embs.shape))
print('Context embeddings shape: %s' % str(tf_context_embs.shape))

# Model
with tf.name_scope('QUESTION_ENCODER'):
    _, question_hidden_states = baseline_model.build_gru(LSTM_HIDDEN_DIM, tf_batch_size,
                                                         [tf_question_embs], config.MAX_QUESTION_WORDS,
                                                         gru_scope='QUESTION_RNN')
with tf.name_scope('CONTEXT_ENCODER'):
    _, context_hidden_states = baseline_model.build_gru(LSTM_HIDDEN_DIM, tf_batch_size,
                                                        [tf_context_embs], config.MAX_CONTEXT_WORDS,
                                                        gru_scope='CONTEXT_RNN')

with tf.name_scope('CONTEXT_ENCODER_REVERSE'):
    _, reverse_context_hidden_states = baseline_model.build_gru(LSTM_HIDDEN_DIM, tf_batch_size,
                                                                [tf_context_embs], config.MAX_CONTEXT_WORDS,
                                                                gru_scope='CONTEXT_RNN_REVERSE', reverse=True)

tf_context_hidden_states = tf.stack(context_hidden_states + reverse_context_hidden_states, axis=1)
print('tf_context_hidden_states shape: %s' % str(tf_context_hidden_states.get_shape()))

tf_weighted_states = attention.attention(tf_context_hidden_states, LSTM_HIDDEN_DIM)  # attention
print('Weighted states shape: %s' % str(tf_weighted_states.get_shape()))

tf_question_context_emb = tf.concat([question_hidden_states[-1], context_hidden_states[-1],
                                     reverse_context_hidden_states[-1], tf_weighted_states], axis=1, name='question_context_emb')
print('tf_question_context_emb shape: %s' % str(tf_question_context_emb.get_shape()))

# answer_outputs, _ = baseline_model.build_gru(LSTM_HIDDEN_DIM, tf_batch_size,
#                                              [], config.MAX_ANSWER_WORDS, time_step_inputs=[tf_question_context_emb],
#                                              gru_scope='ANSWER_RNN')

# tf_vocab_w = tf.Variable(tf.random_normal([LSTM_HIDDEN_DIM, config.MAX_CONTEXT_WORDS + 1]))
# tf_vocab_b = tf.Variable(tf.random_normal([config.MAX_CONTEXT_WORDS + 1]))

# tf_vocab_w = tf.Variable(tf.random_normal([LSTM_HIDDEN_DIM * 2, index_prob_size * 2]), name='prediction_w')
# tf_vocab_b = tf.Variable(tf.random_normal([index_prob_size * 2]), name='prediction_b')

if PREDICT_PROBABILITIES:
    fc_output_size = index_prob_size * 2
else:
    fc_output_size = 2

tf_layer1, tf_prediction1_w, tf_prediction1_b = baseline_model.create_dense_layer(tf_question_context_emb, LSTM_HIDDEN_DIM * 4,
                                                                                   LSTM_HIDDEN_DIM * 2, activation='relu',
                                                                                   name='FIRST_PREDICTION_LAYER')

tf_start_end_indices, tf_prediction2_w, tf_prediction2_b = baseline_model.create_dense_layer(tf_layer1, LSTM_HIDDEN_DIM * 2,
                                                                                   fc_output_size, activation=None,
                                                                                   name='SECOND_PREDICTION_LAYER')

if PREDICT_PROBABILITIES:
    tf_start_prob = tf_start_end_indices[:, :index_prob_size]
    tf_end_prob = tf_start_end_indices[:, index_prob_size:]
    print('tf_start_prob, tf_answer_indices[:, 0]')
    print(tf_start_prob.get_shape())
    print(tf_answer_indices[:, 0].get_shape())
    tf_start_losses = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=tf_start_prob,
                                                                     labels=tf_answer_indices[:, 0])
    tf_end_losses = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=tf_end_prob,
                                                                   labels=tf_answer_indices[:, 1])
    tf_total_loss = tf.reduce_mean(tf_start_losses + tf_end_losses, axis=0)
    tf_start_index = tf.argmax(tf_start_prob, axis=1)
    tf_end_index = tf.argmax(tf_end_prob, axis=1)
    tf_prediction = tf.stack([tf_start_index, tf_end_index], axis=1)
else:
    # Predict real values for indices
    tf_start_index = tf_start_end_indices[:, 0]
    tf_end_index = tf_start_end_indices[:, 1]
    tf_total_loss = tf.nn.l2_loss(tf.cast(tf_answer_indices, tf.float32) - tf_start_end_indices, name='loss') # squared error
    tf_total_loss = tf_total_loss / tf.cast(tf_batch_size, tf.float32)
    tf_prediction = tf.cast(tf.round(tf_start_end_indices), tf.int32)

# vocab_predictions = []
# for each_output in answer_outputs:
#     word_prediction = tf.matmul(each_output, tf_vocab_w) + tf_vocab_b
#     vocab_predictions.append(word_prediction)
#
# predictions_indices = []
# for each_prediction in vocab_predictions:
#     tf_prediction_indices = tf.argmax(each_prediction, axis=1)
#     predictions_indices.append(tf.reshape(tf_prediction_indices, [-1, 1]))
#
# tf_predictions_indices = tf.concat(predictions_indices, axis=1)
#
# print('Model output prediction indices shape: %s' % str(tf_predictions_indices.get_shape()))
# print('RNN output shape: %s' % str(answer_outputs[0].get_shape()))
# print('Labels indices for loss function: %s' % str(tf_answer_indices[:, 0].get_shape()))
# print('Prediction distribution shape: %s' % str(vocab_predictions[0].get_shape()))
#
# tf_total_losses = 0
# for i, each_prediction in enumerate(vocab_predictions):
#     tf_output_loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=each_prediction, labels=tf_answer_indices[:, i])
#     tf_total_losses += tf_output_loss
#
# tf_total_loss = tf.reduce_mean(tf_total_losses, axis=0)
# print('Shape of tf_total_loss: %s' % str(tf_total_loss.get_shape()))
# Visualize
baseline_model.create_tensorboard_visualization('cic')

train_op = tf.train.AdamOptimizer(LEARNING_RATE).minimize(tf_total_loss)
init = tf.global_variables_initializer()
sess = tf.InteractiveSession(config=tf_config)
sess.run(init)

if VALIDATE_PROPER_INPUTS:
    print('Validating proper inputs')
    # Validates that embedding lookups for the first 1000 contexts and questions
    # look up the correct embedding for each index, and that the embedding is
    # the same as that stored in the embedding table and in the spacy nlp object.
    sample_size = 1000
    if sample_size > num_examples:
        sample_size = num_examples
    fd={tf_context_indices: np_contexts[:sample_size, :]}
    np_sample_context_embs = tf_context_embs.eval(fd)
    for i in range(sample_size):
        context_tokens = contexts[i].split()
        for j in range(np_sample_context_embs.shape[1]):
            if j < len(context_tokens):
                word = context_tokens[j]
                word_vector = sdt.nlp(word).vector
                word_index = vocab_dict[word]
                stored_vector = np_embeddings[word_index, :]
                if not np.isclose(word_vector, np.zeros([config.SPACY_GLOVE_EMB_SIZE])).all():
                    assert np.isclose(np_sample_context_embs[i, j, :], word_vector).all()
                    assert np.isclose(np_sample_context_embs[i, j, :], stored_vector).all()
    fd={tf_question_indices: np_questions[:sample_size, :]}
    np_sample_question_embs = tf_question_embs.eval(fd)
    for i in range(sample_size):
        question_tokens = questions[i].split()
        for j in range(np_sample_question_embs.shape[1]):
            if j < len(question_tokens):
                word = question_tokens[j]
                word_index = vocab_dict[word]
                stored_vector = np_embeddings[word_index, :]
                word_vector = sdt.nlp(word).vector
                if not np.isclose(word_vector, np.zeros([config.SPACY_GLOVE_EMB_SIZE])).all():
                    assert np.isclose(np_sample_question_embs[i, j, :], word_vector).all()
                    assert np.isclose(np_sample_question_embs[i, j, :], stored_vector).all()
    print('Inputs validated')

print('Training model...')
batch_size = 20
num_batches = int(num_examples * TRAIN_FRAC / batch_size)
num_train_examples = batch_size * num_batches

for epoch in range(NUM_EPOCHS):
    print('Epoch: %s' % epoch)
    losses = []
    accuracies = []
    for i in range(num_batches):
        np_question_batch = np_questions[i*batch_size:i*batch_size+batch_size, :]
        np_answer_batch = np_answers[i*batch_size:i*batch_size+batch_size, :]
        np_context_batch = np_contexts[i*batch_size:i*batch_size+batch_size, :]
        np_batch_predictions, np_loss, _ = sess.run([tf_prediction, tf_total_loss, train_op],
                                                    feed_dict={tf_question_indices: np_question_batch,
                                                               tf_answer_indices: np_answer_batch,
                                                               tf_context_indices: np_context_batch,
                                                               tf_batch_size: batch_size})
        accuracy = sdt.compute_multi_label_accuracy(np_answer_batch, np_batch_predictions)
        accuracies.append(accuracy)
        losses.append(np_loss)
    epoch_loss = np.mean(losses)
    epoch_accuracy = np.mean(accuracies)
    print('Epoch loss: %s' % epoch_loss)
    print('TRAIN EM Score: %s' % epoch_accuracy)

print('Predicting...')
val_index_start = batch_size * num_batches
np_train_predictions = sess.run(tf_prediction, feed_dict={tf_question_indices: np_questions[:val_index_start, :],
                                                    tf_answer_indices: np_answers[:val_index_start, :],
                                                    tf_context_indices: np_contexts[:val_index_start, :],
                                                    tf_batch_size: num_train_examples})

total_train_accuracy = sdt.compute_multi_label_accuracy(np_train_predictions, np_answers[:val_index_start, :])

print('TRAIN EM Score: %s' % total_train_accuracy)

# Print training examples
predictions = sdt.convert_numpy_array_answers_to_strings(np_train_predictions[:NUM_EXAMPLES_TO_PRINT, :],
                                                         contexts[:NUM_EXAMPLES_TO_PRINT],
                                                         answer_is_span=True)
for i, each_prediction in enumerate(predictions):
    print('Prediction: %s' % each_prediction)
    print('Answer: %s' % examples[i][1])
    print('Answer array: %s' % np_answers[i, :])
    print('Prediction array: %s' % np_train_predictions[i, :])
    print('Question: %s' % examples[i][0])
    print('Len context: %s' % len(contexts[i]))
    print()
print('\n######################################\n')
# Must generate validation predictions in batches to avoid OOM error
num_val_examples = num_examples - val_index_start
num_val_batches = int(num_val_examples / batch_size) + 1  # +1 to include remainder examples
all_val_predictions = []
for batch_index in range(num_val_batches):
    current_start_index = batch_size * batch_index
    if current_start_index + batch_size >= num_val_examples:
        effective_batch_size = num_val_examples - current_start_index
    else:
        effective_batch_size = batch_size
    current_end_index = current_start_index + effective_batch_size
    np_batch_val_predictions = sess.run(tf_prediction, feed_dict={tf_question_indices: np_questions[current_start_index:current_end_index, :],
                                                            tf_answer_indices: np_answers[current_start_index:current_end_index, :],
                                                            tf_context_indices: np_contexts[current_start_index:current_end_index, :],
                                                            tf_batch_size: effective_batch_size})
    all_val_predictions.append(np_batch_val_predictions)
np_val_predictions = np.concatenate(all_val_predictions, axis=0)

# Print validation examples
predictions = sdt.convert_numpy_array_answers_to_strings(np_val_predictions[:NUM_EXAMPLES_TO_PRINT, :],
                                                         contexts[val_index_start:val_index_start+NUM_EXAMPLES_TO_PRINT],
                                                         answer_is_span=True)
for i, each_prediction in enumerate(predictions):
    print('Prediction: %s' % each_prediction)
    print('Answer: %s' % examples[val_index_start + i][1])
    print('Answer array: %s' % np_answers[val_index_start + i, :])
    print('Prediction array: %s' % np_val_predictions[i, :])
    print('Question: %s' % examples[val_index_start + i][0])
    print('Len context: %s' % len(contexts[val_index_start + i]))
    print('Context: %s' % contexts[val_index_start + i])
    print()

val_accuracy = sdt.compute_multi_label_accuracy(np_val_predictions, np_answers[val_index_start:])

print('VAL EM Score: %s' % val_accuracy)

print('Prediction shape: %s' % str(np_val_predictions.shape))



















