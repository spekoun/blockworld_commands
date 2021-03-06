
import tensorflow as tf
from setting import max_command_len
import numpy as np
import pdb
from utils import get_embedding_matrix, get_word_characters, vocabulary_length


class Network:
    def __init__(self, network_type, run_id, initial_learning_rate, target, rnn_cell_type, rnn_cell_dim, bidirectional, hidden_dimension, 
                            use_world, dropout_input, dropout_output, embeddings, version, threads, use_tags, rnn_output, hidden_layers, 
                            use_logos, use_source_flags, distinct_x_y, seed, optimizer_type, gradient_clipping, world_dimension = 2):
        self.target = target
        self.dropout_input = dropout_input
        self.dropout_output = dropout_output
        self.use_tags = use_tags
        self.rnn_layers_created = 0

        if run_id == 5123:
            self.old_graph = True
        else:
            self.old_graph = False

        graph = tf.Graph()
        graph.seed = seed
        self.session = tf.Session(graph = graph, config = tf.ConfigProto(inter_op_parallelism_threads = threads, intra_op_parallelism_threads = threads))

        self.summary_writer = tf.summary.FileWriter("logs/" + str(run_id) + "_" + target + "_" + network_type, flush_secs=10)

        with self.session.graph.as_default():
            self.command = tf.placeholder(tf.int32, [None, max_command_len])          #[batch, sentence_length]
            self.command_lens = tf.placeholder(tf.int32, [None])
            self.tags = tf.placeholder(tf.int32, [None, max_command_len])
            self.world = tf.placeholder(tf.float32, [None, 20 * world_dimension])     #[batch, block_coordinates]
            self.source = tf.placeholder(tf.int32, [None])
            self.location = tf.placeholder(tf.float32, [None, world_dimension])
            self.logos = tf.placeholder(tf.bool, [None])
            self.source_flags = tf.placeholder(tf.int32, [None, max_command_len])

            self.dropout_input_tensor = tf.placeholder(tf.float32, shape = ())
            self.dropout_output_tensor = tf.placeholder(tf.float32, shape = ())
            self.dropout_input_multiplier = tf.placeholder(tf.float32, shape = ())
            self.dropout_output_multiplier = tf.placeholder(tf.float32, shape = ())
            self.variable_learning_rate = tf.placeholder(tf.float32, shape = ())

            ################################## EMBEDDINGS ############################
            embedding_dim = 50
            if embeddings == "none":
                self.embedded_words = tf.one_hot(self.command, vocabulary_length(version))

            elif embeddings == "random":
                self.embeddings = tf.Variable(tf.random_uniform([vocabulary_length(version), embedding_dim], minval = -1, maxval = 1))
                self.embedded_words = tf.gather(self.embeddings, self.command)

            elif embeddings == "pretrained":
                self.embeddings = tf.Variable(initial_value = get_embedding_matrix(version))
                self.embedded_words = tf.gather(self.embeddings, self.command)
            
            elif embeddings == "static_pretrained":
                self.embeddings = tf.Variable(initial_value = get_embedding_matrix(version), trainable=False)
                self.embedded_words = tf.gather(self.embeddings, self.command)

            elif embeddings == "character":
                char_rnn_cell = tf.contrib.rnn.GRUCell(embedding_dim)
                word_to_chars, num_chars, word_lens = get_word_characters(version)
                self.word_to_chars = tf.constant(word_to_chars)     # [number_of_words, max_word_len]
                self.word_lens = tf.constant(word_lens)             # [number_of_words]
                self.command_in_chars = tf.gather(self.word_to_chars, self.command) # [batch_size, max_command_len, max_word_len]
                self.command_word_lens = tf.gather(self.word_lens, self.command)    # [batch_size, max_command_len]

                self.character_embeddings = tf.Variable(tf.random_uniform([num_chars, embedding_dim], minval = -1, maxval = 1))
                self.embedded_chars = tf.gather(self.character_embeddings, self.command_in_chars)       # [batch_size, max_command_len, max_word_len, embedding_dim]
                self.embedded_chars_concat = tf.reshape(self.embedded_chars, [-1, max(word_lens), embedding_dim])
                self.command_word_lens = tf.reshape(self.command_word_lens, [-1])
                _, self.embedded_words = tf.nn.dynamic_rnn(char_rnn_cell, self.embedded_chars_concat, sequence_length = self.command_word_lens, dtype = tf.float32)
                self.embedded_words = tf.reshape(self.embedded_words, [-1, max_command_len, embedding_dim])
            
            elif embeddings == "character_variant":
                char_rnn_cell = tf.contrib.rnn.LSTMCell(embedding_dim / 2)
                word_to_chars, num_chars, word_lens = get_word_characters(version)
                self.word_to_chars = tf.constant(word_to_chars)     # [number_of_words, max_word_len]
                self.word_lens = tf.constant(word_lens)             # [number_of_words]
                self.command_in_chars = tf.gather(self.word_to_chars, self.command) # [batch_size, max_command_len, max_word_len]
                self.command_word_lens = tf.gather(self.word_lens, self.command)    # [batch_size, max_command_len]

                self.character_embeddings = tf.Variable(tf.random_uniform([num_chars, int(embedding_dim / 2)], minval = -1, maxval = 1))
                self.embedded_chars = tf.gather(self.character_embeddings, self.command_in_chars)       # [batch_size, max_command_len, max_word_len, embedding_dim]
                self.embedded_chars_concat = tf.reshape(self.embedded_chars, [-1, max(word_lens), int(embedding_dim / 2)])
                self.command_word_lens = tf.reshape(self.command_word_lens, [-1])
                _, self.embedded_words = tf.nn.bidirectional_dynamic_rnn(char_rnn_cell, char_rnn_cell, self.embedded_chars_concat, sequence_length = self.command_word_lens, dtype = tf.float32)
                self.embedded_words = tf.concat(axis = 1, values = [self.embedded_words[0].c, self.embedded_words[1].c])
                self.embedded_words = tf.reshape(self.embedded_words, [-1, max_command_len, embedding_dim])

            ################################# TAGS ####################################
            if use_tags:
                tag_dim = 10
                self.tag_embeddings = tf.Variable(tf.random_uniform([vocabulary_length(version), tag_dim], minval = -1, maxval = 1))
                self.embedded_tags = tf.gather(self.tag_embeddings, self.tags)
                self.embedded_words = tf.concat(axis=2, values=[self.embedded_words, self.embedded_tags])
            
            ############################### LOGOS ###################################

            if use_logos:
                self.logos_multiple_times = tf.reshape(tf.tile(self.logos, [max_command_len]), [-1, max_command_len, 1])
                self.embedded_words = tf.concat(axis=2, values = [self.embedded_words, tf.to_float(self.logos_multiple_times)])

            ############################### SOURCE INPUT ##################################

            if use_source_flags:
                assert target == "location"
                self.source_flags_reshaped = tf.reshape(self.source_flags, [-1, max_command_len, 1])
                self.embedded_words = tf.concat(axis=2, values = [self.embedded_words, tf.to_float(self.source_flags_reshaped)])

            ############################### DROPOUT INPUT ############################
            if not self.old_graph:
                self.rnn_input = tf.scalar_mul(self.dropout_input_multiplier, tf.nn.dropout(self.embedded_words, 1.0 - self.dropout_input_tensor))
            elif self.old_graph:
                self.rnn_input = tf.nn.dropout(self.embedded_words, 1.0 - self.dropout_input_tensor)

            ############################## HIDDEN LAYERS #############################

            if network_type == "rnn":
               
                if hidden_layers > 1:
                    self.rnn_input = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, rnn_cell_dim, hidden_layers - 1, "all_outputs", self.dropout_output_tensor, self.dropout_output_multiplier)
                    if not self.old_graph:
                        self.rnn_input = tf.scalar_mul(self.dropout_output_multiplier, tf.nn.dropout(self.rnn_input, 1.0 - self.dropout_output_tensor))
                    else:
                        self.rnn_input = tf.nn.dropout(self.rnn_input, 1.0 - self.dropout_output_tensor)
                
                if rnn_output in ["last_state", "output_sum"]:
                    if rnn_output == "last_state":
                        self.hidden_layer = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, rnn_cell_dim, 1, "last_state")
                    
                    elif rnn_output == "output_sum":
                        self.hidden_layer = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, rnn_cell_dim, 1, "output_sum")
                    
                    self.hidden_layer = tf.nn.dropout(self.hidden_layer, 1.0 - self.dropout_output_tensor)
                    
                    if use_world:
                        self.hidden_layer = tf.concat(axis=1, values=[self.hidden_layer, self.world])
                    
                    if distinct_x_y:
                        self.reference = tf.contrib.layers.fully_connected(self.hidden_layer, num_outputs = 40, activation_fn = None)
                        self.location_by_direction = tf.contrib.layers.fully_connected(self.hidden_layer, num_outputs = world_dimension, activation_fn = None)
                    else:
                        self.reference = tf.contrib.layers.fully_connected(self.hidden_layer, num_outputs = 20, activation_fn = None)
                        self.location_by_direction = tf.contrib.layers.fully_connected(self.hidden_layer, num_outputs = world_dimension, activation_fn = None)

                    self.logits = tf.contrib.layers.fully_connected(self.hidden_layer, num_outputs = 20, activation_fn = None)

                elif rnn_output in ["direct_last_state", "direct_output_sum"]:
                    if rnn_output == "direct_last_state":
                        output_type = "last_state_sum"
                    elif rnn_output == "direct_output_sum":
                        output_type = "output_sum"

                    if distinct_x_y:
                        self.reference = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, 40, 1, output_type)
                        self.location_by_direction = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, world_dimension, 1, output_type)
                    else:
                        self.reference = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, 20, 1, output_type)
                        self.location_by_direction = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, world_dimension, 1, output_type)

                    self.logits = self.rnn_layers(self.rnn_input, self.command_lens, rnn_cell_type, 20, 1, output_type)
                           
            elif network_type == "ffn":
                self.ffn_input = tf.cast(tf.contrib.layers.flatten(self.rnn_input), tf.float32)

                if use_world:
                    self.ffn_input = tf.concat(axis = 1, values = [self.world, self.ffn_input])

                for i in range(hidden_layers):
                    self.ffn_input = tf.contrib.layers.fully_connected(self.ffn_input, num_outputs = hidden_dimension, activation_fn = tf.nn.relu)
                    self.ffn_input = tf.nn.dropout(self.ffn_input, 1.0 - self.dropout_output_tensor)
               
                self.reference = tf.contrib.layers.fully_connected(self.ffn_input, num_outputs = 20, activation_fn = None)
                self.location_by_direction = tf.contrib.layers.fully_connected(self.ffn_input, num_outputs = world_dimension, activation_fn = None)
                self.logits = tf.contrib.layers.fully_connected(self.ffn_input, num_outputs = 20, activation_fn = None)
                
            else:
                print(network_type)
                assert False
            
            ################################### OUTPUT LAYER #########################
            
            if target == "source":
                self.predicted_source = tf.argmax(self.logits, 1)
                self.accuracy = tf.contrib.metrics.accuracy(tf.to_int32(self.predicted_source), self.source)
                self.loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=self.logits, labels=self.source)

            elif target == "location":
                if use_world:
                    self.predicted_location = self.location_by_direction
                else:
                #    scale = True
                #    if scale:
                #        self.reference_sum = tf.reduce_sum(self.reference, axis = 1)
                #        self.reference_sum = tf.reshape(tf.stack([self.reference_sum] * 20, axis = 1), [-1, 20])
                #        self.reference = self.reference / self.reference_sum
                
                    if distinct_x_y:
                        self.reference_stacked = tf.reshape(self.reference, [-1, 20, world_dimension])
                    else:
                        self.reference_stacked = tf.stack([self.reference] * world_dimension, axis=2)   #[batch, 20, world_dimension]
                    
                    self.world_reshaped = tf.reshape(self.world, [-1, 20, world_dimension])
                    self.multiple = tf.multiply(self.reference_stacked, self.world_reshaped)
                    self.location_by_reference = tf.reduce_sum(self.multiple, axis = 1)
                    
                    self.predicted_location = tf.add(self.location_by_reference, self.location_by_direction)
                
                self.average_distance = tf.reduce_mean(tf.sqrt(tf.reduce_sum(tf.square(self.location - self.predicted_location), axis = 1)))
            
                square_error = False
                if square_error:
                    self.loss = tf.reduce_mean(tf.reduce_sum(tf.square(self.location - self.predicted_location), axis = 1))
                else:
                    self.loss = self.average_distance
             
            else:
                print(target)
                assert False
            

            ############################## OPTIMIZER ####################################################

            if self.old_graph:
                self.training = tf.train.AdamOptimizer(initial_learning_rate).minimize(self.loss)
            
            else:
                global_step = tf.Variable(0, trainable=False)

                if optimizer_type[0:3] == "SGD":
                    optimizer_constructor = tf.train.GradientDescentOptimizer
                elif optimizer_type[0:4] == "Adam":
                    optimizer_constructor = tf.train.AdamOptimizer
                else:
                    print(optimizer_type)
                    assert False

                if optimizer_type == "SGD_exponential_decay" or optimizer_type == "Adam_exponential_decay":
                    learning_rate = tf.train.exponential_decay(initial_learning_rate, global_step, 100000, 0.96, staircase=True)
                    optimizer = optimizer_constructor(learning_rate)

                elif optimizer_type == "SGD_variable_decay" or optimizer_type == "Adam_variable_decay":
                    optimizer = optimizer_constructor(self.variable_learning_rate)

                elif optimizer_type == "SGD" or optimizer_type == "Adam":
                    optimizer = optimizer_constructor(initial_learning_rate)

            ############################## GRADIENT CLIPPING ###########################################

                if not gradient_clipping:
                    self.training = optimizer.minimize(self.loss, global_step = global_step)
                else:
                    gradient_min = -1.0
                    gradient_max = 1.0
                    gradients = optimizer.compute_gradients(self.loss)
                
                    clipped_gradients = []
                    for gradient in gradients:
                        if gradient[0] is None:
                            clipped_gradients.append(gradient)
                            continue
                            
                        clipped = tf.clip_by_value(gradient[0], gradient_min, gradient_max)
                        clipped = (clipped, gradient[1])
                        clipped_gradients.append(clipped)

                    self.training = optimizer.apply_gradients(clipped_gradients, global_step = global_step)

            if target == "source":
                self.train_summary = tf.summary.scalar("train/accuracy", self.accuracy)
                self.test_summary = tf.summary.scalar("test/accuracy", self.accuracy)
                self.dev_summary = tf.summary.scalar("dev/accuracy", self.accuracy)

            elif target == "location":
                self.train_summary = tf.summary.scalar("train/distance", self.average_distance)
                self.test_summary = tf.summary.scalar("test/distance", self.average_distance)
                self.dev_summary = tf.summary.scalar("dev/distance", self.average_distance)

            self.saver = tf.train.Saver()

            init = tf.global_variables_initializer()
            self.session.run(init)
    
    
    def rnn_layers(self, rnn_input, sequence_length, rnn_cell_type, rnn_cell_dim, layers, output, dropout_hidden = 0, dropout_multiplier = 1):
        assert layers > 0

        if rnn_cell_type == "LSTM":
            rnn_cell = tf.contrib.rnn.LSTMCell(rnn_cell_dim)

        elif rnn_cell_type == "GRU":
            rnn_cell = tf.contrib.rnn.GRUCell(rnn_cell_dim)

        else:
            raise ValueError("RNN cell type must be 'LSTM' or 'GRU'")
        
        for i in range(0, layers):
            scope = "rnn_layer_" + str(self.rnn_layers_created)
            self.rnn_layers_created += 1
            rnn_output, rnn_state = tf.nn.bidirectional_dynamic_rnn(rnn_cell, rnn_cell, rnn_input, sequence_length = sequence_length, dtype = tf.float32, scope = scope)
            rnn_input = tf.concat(axis=2, values=[rnn_output[0], rnn_output[1]])
            if not self.old_graph:
                rnn_input = tf.scalar_mul(dropout_multiplier, tf.nn.dropout(rnn_input, 1.0 - dropout_hidden))
            else:
                rnn_input = tf.nn.dropout(rnn_input, 1.0 - dropout_hidden)

        if output == "last_state":
            if rnn_cell_type == "LSTM":
                rnn_output = tf.concat(axis=1, values=[rnn_state[0].c, rnn_state[1].c])
            else:
                rnn_output = tf.concat(axis=1, values=rnn_state)
        
        elif output == "last_state_sum":                #sum both bidirectional last states
            if rnn_cell_type == "LSTM":
                rnn_output = tf.reduce_sum([rnn_state[0].c, rnn_state[1].c], 0)
            else:
                rnn_output = tf.reduce_sum(rnn_state, 0)

        elif output == "output_sum":
            concatenated_outputs = tf.concat(axis=2, values=[rnn_output[0], rnn_output[1]])
            rnn_output = tf.reduce_sum(concatenated_outputs, 1)
        
        elif output == "all_outputs":
            rnn_output = tf.concat(axis=2, values=[rnn_output[0], rnn_output[1]])
            
        else:
            assert False

        return rnn_output


    def get_command_lens(self, commands):
        command_lens = []
        for command in commands:
            command_lens.append(np.where(command == 1)[0][0] + 1)

        return command_lens
     

    def select_summary(self, dataset):
        if dataset == "dev":
            return self.dev_summary
        elif dataset == "test":
            return self.test_summary
        elif dataset == "train":
            return self.train_summary
        
        assert False


    def get_dropout_multiplier(self, dropout):
        if self.target == "source":
            return 1.0
        else:
            return 1.0 - dropout


    def predict(self, commands, world, source_id, location, tags, logos, source_flags, dataset, generate_summary = True):
        predicted_location = None
        predicted_source = None
        feed_dict = {self.command : commands, self.command_lens : self.get_command_lens(commands), self.world : world, self.source : source_id, self.location : location,
                            self.dropout_input_tensor : 0.0, self.dropout_output_tensor : 0.0, self.dropout_input_multiplier : self.get_dropout_multiplier(self.dropout_input),
                            self.dropout_output_multiplier : self.get_dropout_multiplier(self.dropout_output), self.tags : tags, self.logos : logos, self.source_flags : source_flags}

        if generate_summary:
            if self.target == "location":
                predicted_location, summary = self.session.run([self.predicted_location, self.select_summary(dataset)], feed_dict)

            elif self.target == "source":
                predicted_source, summary = self.session.run([self.predicted_source, self.select_summary(dataset)], feed_dict)

            self.summary_writer.add_summary(summary)
        
        else:
            if self.target == "location":
                predicted_location = self.session.run([self.predicted_location], feed_dict)

            elif self.target == "source":
                predicted_source = self.session.run([self.predicted_source], feed_dict)

        return predicted_source, predicted_location

    
    def get_reference(self, commands, world, source_id, location, tags, logos, source_flags, dataset, learning_rate):
        feed_dict = {self.command : commands, self.command_lens : self.get_command_lens(commands), self.world : world, self.source : source_id, self.location : location,
                            self.dropout_input_tensor : 0.0, self.dropout_output_tensor : 0.0, self.dropout_input_multiplier : self.get_dropout_multiplier(self.dropout_input),
                            self.dropout_output_multiplier : self.get_dropout_multiplier(self.dropout_output), self.tags : tags, self.logos : logos, self.source_flags : source_flags}

        if self.target == "location": 
            reference, location_reference, location_direction = self.session.run([self.reference, self.location_by_reference, self.location_by_direction], feed_dict)

        else:
            assert False

        return reference, location_reference, location_direction

    
    def train(self, commands, world, source_id, location, tags, logos, source_flags, learning_rate):
        feed_dict = {self.command : commands, self.command_lens : self.get_command_lens(commands), self.world : world, self.source : source_id, self.location : location,
                            self.dropout_input_tensor : self.dropout_input, self.dropout_output_tensor : self.dropout_output, self.dropout_input_multiplier : 1.0, self.dropout_output_multiplier : 1.0,
                            self.tags : tags, self.logos : logos, self.source_flags : source_flags, self.variable_learning_rate : learning_rate}

        debug = False
        if debug == False:
            _, summary, loss  = self.session.run([self.training, self.select_summary("train"), self.loss], feed_dict)

        else:
            _, summary, loss, hidden, reference, location_reference, location_direction = self.session.run([self.training, self.select_summary("train"), self.loss, self.hidden_layer, self.reference, self.location_by_reference, self.location_by_direction], feed_dict)
                        
                       
        if debug:
            print("Reference: " + str(reference[0]))
            print("Location reference: " + str(location_reference[0]))
            print("Location direction: " + str(location_direction[0]))

        self.summary_writer.add_summary(summary)



