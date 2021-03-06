
from dataset import Dataset
from scipy.spatial import distance
import copy
import random
import numpy as np
from network import Network
from benchmark_model import BenchmarkModel
from baseline import RandomBaseline
from baseline import DeterministicBaseline
import argparse
from database import Database
import pdb
import tensorflow as tf
import time
import os.path
import ast
from drawer import Drawer
from setting import logos
from utils import convert_world


def evaluate(model, dataset, epoch, dimension = 2):
    commands, worlds, sources, locations, tags, logos, source_flags = dataset.get_all_data()
    #raw_commands, _, _, _ = dataset.get_raw_commands_and_logos()
    predicted_sources, predicted_locations = model.predict(commands, worlds, sources, locations, tags, logos, source_flags, dataset.dataset_name)
 
    source_accuracy = None
    location_distance = None
    correct_percentage = None

    if predicted_sources is not None:
        source_correct = 0
        for i in range(0, len(commands)):
            if sources[i] == predicted_sources[i]:
                source_correct += 1
        
        source_accuracy = source_correct / float(len(commands))

    if predicted_locations is not None:    
        location_errors = []
        correct = 0
        location_difference = 0
        for i in range(0, len(commands)):
            location_difference += distance.euclidean(predicted_locations[i], locations[i])
            location_errors.append(distance.euclidean(predicted_locations[i], locations[i]))
            #if abs(predicted_locations[i][0] - locations[i][0]) <= 0.5 and abs(predicted_locations[i][1] - locations[i][1]) <= 0.5:
            if is_correct(predicted_locations[i], locations[i]):
                correct += 1

        location_distance = location_difference / float(len(commands))

        #correct_percentage = len([x for x in location_errors if x < 0.5]) / len(location_errors)
        correct_percentage = correct / len(location_errors)
#        print("Less than 0.5 distance: " + str(correct_percentage))

    return (source_accuracy, location_distance, correct_percentage, epoch)


def create_images(run_id):  
    args = load_args(run_id)
    model = load_model(args, run_id)
    dataset = Dataset("dev", args["version"])
    benchmark = BenchmarkModel(version = args["version"], target = "source")

    commands, worlds, sources, locations, tags, is_logos, source_flags = dataset.get_all_data()
    raw_commands, is_logos, command_ids, tokenized = dataset.get_raw_commands_and_logos()

    predicted_sources, predicted_locations = model.predict(commands, worlds, sources, locations, tags, is_logos, source_flags, dataset.dataset_name)

    drawer = Drawer("./images/" + str(run_id))

    if predicted_sources is None:
        predicted_sources = sources
        target_info = "Predicting location"
        predicting_source = False
        references, location_references, location_directions = model.get_reference(commands, worlds, sources, locations, tags, is_logos, source_flags, dataset.dataset_name, args["learning_rate"])

    elif predicted_locations is None:
        predicted_locations = locations
        target_info = "Predicting source"
        predicting_source = True

    for i in range(0, len(predicted_locations)):
        world_before = convert_world(worlds[i])
        world_after = convert_world(worlds[i])
        world_after[predicted_sources[i]] = predicted_locations[i]

        result = ""
        result_description = ""
        reference_description = ""
        correct_location = None
        if predicting_source:
            if not is_logos[i]:
                result_description = "predicted: " + str(predicted_sources[i] + 1) + ", correct: " + str(sources[i] + 1)
            else:
                result_description = "predicted: " + str(logos[predicted_sources[i]]) + ", correct: " + str(logos[sources[i]])
            if predicted_sources[i] == sources[i]:
                result = "correct"
            else:
                result = "wrong"
        else:
            result = str(distance.euclidean(predicted_locations[i], locations[i]))
            result_description = "predicted: " + str(predicted_locations[i]) + ", correct: " + str(locations[i])
            for j in range(20):
                if len(references[i]) == 20:
                    reference_text = format(references[i][j], ".2f")
                elif len(references[i]) == 40:      #distinct x y -> 40 weights
                    reference_text = format(references[i][2*j], ".2f") + "," + format(references[i][2*j + 1], ".2f")
                else:
                    reference_text = ""

                if is_logos[i]:
                    reference_description += logos[j] + ": " + reference_text + ", "
                else:
                    reference_description += str(j + 1) + ": " + reference_text + ", "

                if j % 8 == 7:
                    reference_description += "\n"
            

            reference_description += "\nreference: " + str(location_references[i]) + ", direction: " + str(location_directions[i])
            correct_location = locations[i]
        
        other_info = target_info + ", " + str(command_ids[i]) + ", " + result_description + ", " + result + "\n\n" + reference_description
        command_category = get_command_category(commands[i], is_logos[i], benchmark)
        category_shortcut = get_category_shortcut(command_category)
        filename = result + "_" + str(command_ids[i]) + "_" + str(category_shortcut)

        drawer.save_image(raw_commands[i] + "\n" + str(tokenized[i]), world_before, world_after, is_logos[i], other_info, filename, correct_location, predicted_sources[i])


def improvement(best_results, current_results):
    if current_results[0] is not None:
        return best_results[0] < current_results[0]

    if current_results[1] is not None:
        return best_results[1] > current_results[1]

    assert False


def print_results(results):
    print("Epoch: " + str(results[3]))
    if results[0] is not None:
        print("Source accuracy: " + str(results[0]))
    
    if results[1] is not None:
        print("Location distance: " + str(results[1]))
        print("Correct: " + str(results[2]))
    
    print("")


def save(run_id, args, dev_results, test_results, start_time):
    epoch = dev_results[3]
    if args["target"] == "source":
        dev_result = dev_results[0]
        test_result = test_results[0]
        correct_dev = None
        correct_test = None
    else:
        dev_result = dev_results[1]
        test_result = test_results[1]
        correct_dev = dev_results[2]
        correct_test = test_results[2]

    args["run_id"] = run_id

    seconds = (time.time() - start_time) * args["threads"]
    computation_time = str(int(seconds / 3600)) + ":" + str(int(seconds / 60) % 60)

    db_cols = ["run_id", "target", "model", "version", "dev_result", "test_result", "correct_dev", "correct_test", "epoch", "hidden_dimension", "learning_rate", "rnn_cell_dim", "rnn_cell_type", "bidirectional", "dropout_input", "dropout_output", "batch_size", "use_world", "embeddings", "hidden_layers", "rnn_output", "use_tags", "use_logos", "distinct_x_y", "seed", "computation_time", "generated_commands", "switch_blocks", "source_flags", "optimizer_type", "gradient_clipping", "comment", "args"]
    
    args_to_process = copy.deepcopy(args)
    args_to_delete = ["max_epochs", "test", "restore_and_test", "threads", "stop", "create_images", "continue_training", "analyze"]
    if args_to_process["model"] == "ffn":
        args_to_delete += ["rnn_cell_type", "rnn_cell_dim", "bidirectional", "rnn_output"]
    
    for to_delete in args_to_delete:
        if to_delete in args.keys():
            del args_to_process[to_delete]

    row = []
    
    for col in db_cols:
        if col in args_to_process.keys():
            row.append(args_to_process[col])
            del args_to_process[col]
        elif col in ["run_id", "dev_result", "test_result", "computation_time", "epoch", "correct_dev", "correct_test"]:
            row.append(eval(col))
        elif col in ["args"]:
            row.append(str(args_to_process))
        else:
            row.append(None)

    success = False
    try:
        db = Database()
        db.insert("Results", row)
        success = True
    except pymysql.err.OperationalError:
        try:
            db.close()
            db = Database()
            db.insert("Results", row)
            success = True
        except pymysql.err.OperationalError:
            pass

    if not success:
        print("Writing to output file, mysql server has gone away...")
        output_file = open("error_file_" + str(run_id), "w")
        output_file.write(str(args))
        output_file.write(str(dev_results))


def get_run_id():
    if os.path.isfile(".id"):
        f = open(".id", "r+")
        run_id = int(f.read()) + 1
        f.seek(0)
        f.write(str(run_id))
        f.truncate()

    else:
        run_id = 0
        f = open(".id", "w")
        f.write(str(0))
    
    f.close()
    return run_id


def to_bool(string):
    if string is None:  
        return None

    else:
        return bool(int(string))


def load_args(run_id):
    db = Database()
    db_output = db.get_all_rows("SELECT * FROM Results WHERE RunID = " + str(run_id))
    if len(db_output) != 1:
        raise ValueError("No data in database for run_id: " + str(run_id))

    row = list(db_output[0])
 
    args = ast.literal_eval(row[-1])
    args["target"] = row[1]
    args["network_type"] = row[2]
    args["version"] = row[3]
    args["epoch"] = row[8]
    args["hidden_dimension"] = row[9]
    args["learning_rate"] = row[10]
    args["rnn_cell_dim"] = row[11]
    args["rnn_cell_type"] = row[12]
    args["bidirectional"] = to_bool(row[13])
    args["dropout_input"] = row[14]
    args["dropout_output"] = row[15]
    args["batch_size"] = row[16]
    args["use_world"] = to_bool(row[17])
    args["embeddings"] = row[18]
    args["hidden_layers"] = row[19]
    args["rnn_output"] = row[20]
    args["use_tags"] = to_bool(row[21])
    args["use_logos"] = to_bool(row[22])
    args["distinct_x_y"] = to_bool(row[23])
    args["seed"] = row[24]
    args["generated_commands"] = row[26]
    args["switch_blocks"] = row[27]
    args["source_flags"] = to_bool(row[28])
    args["optimizer_type"] = row[29]
    args["gradient_clipping"] = to_bool(row[30])

    if args["network_type"] == "ffn":
        args["rnn_cell_type"] = 'GRU'
        args["rnn_cell_dim"] = 0
        args["bidirectional"] = True

    return args


def load_best_result(run_id):
    db = Database()
    db_output = db.get_all_rows("SELECT * FROM Results WHERE RunID = " + str(run_id))
    if len(db_output) != 1:
        return (0.0, 1000000.0, 0.0, 0)

    row = list(db_output[0])
 
    if row[1] == "source":
        return (row[4], 1000000, None, row[8])
    else:
        return (0.0, row[4], row[6], row[8])


def load_model(args, run_id):
    if args["network_type"] == "benchmark":
        model = BenchmarkModel(args["version"], target = args["target"])
        return model

    elif args["network_type"] == "random_baseline":
        model = RandomBaseline(target = args["target"])
        return model
     
    elif args["network_type"] == "deterministic_baseline":
        model = DeterministicBaseline(target = args["target"])
        return model
    
    model = Network(args["network_type"], hidden_dimension = args["hidden_dimension"], run_id = run_id, initial_learning_rate = args["learning_rate"], target = args["target"],
                        rnn_cell_dim = args["rnn_cell_dim"], rnn_cell_type = args["rnn_cell_type"], bidirectional = args["bidirectional"], use_world = args["use_world"], 
                        dropout_input = args["dropout_input"], dropout_output = args["dropout_output"], embeddings = args["embeddings"], version = args["version"], 
                        use_tags = args["use_tags"], rnn_output = args["rnn_output"], hidden_layers = args["hidden_layers"], use_logos = args["use_logos"], use_source_flags = args["source_flags"],
                        seed = args["seed"], distinct_x_y = args["distinct_x_y"], optimizer_type = args["optimizer_type"], gradient_clipping = args["gradient_clipping"], threads = 1)

    checkpoint = tf.train.get_checkpoint_state("checkpoints/" + str(run_id))
    model.saver.restore(model.session, checkpoint.model_checkpoint_path)
    return model


def test_model(run_id, test_dataset = True):
    args = load_args(run_id)
    model = load_model(args, run_id)
    if test_dataset:
        dataset = Dataset("test", args["version"])
    else:
        dataset = Dataset("dev", args["version"])

    test_results = evaluate(model, dataset, args["epoch"])
    print_results(test_results)

    db = Database()
    
    if test_results[0] != None:
        test_result = test_results[0]
    else:
        test_result = test_results[1]
        if test_dataset:
            db.execute("UPDATE Results SET CorrectTest = " + str(test_results[2]) + " WHERE RunID = " + str(run_id))
        else:
            db.execute("UPDATE Results SET CorrectDev = " + str(test_results[2]) + " WHERE RunID = " + str(run_id))
    
    if test_dataset:
        db.execute("UPDATE Results SET TestResult = " + str(test_result) + " WHERE RunID = " + str(run_id))
    else:
        db.execute("UPDATE Results SET DevResult = " + str(test_result) + " WHERE RunID = " + str(run_id))


def annotate_data(run_id = 5123):
    args = load_args(run_id)
    model = load_model(args, run_id)
    db = Database()
    
    for dataset_name in ["train", "dev", "test"]:
        dataset = Dataset(dataset_name, args["version"])
        
        commands, worlds, sources, locations, tags, logos, source_flags = dataset.get_all_data()
        raw_commands, logos, command_ids, tokenized = dataset.get_raw_commands_and_logos()
        
        for i in range(0, len(commands)):
            predicted_source, predicted_location = model.predict(commands[i:i+1], worlds[i:i+1], sources[i:i+1], locations[i:i+1], tags[i:i+1], logos[i:i+1], source_flags[i:i+1], dataset_name)
            assert predicted_location == None
            db.execute("UPDATE ModelInput SET PredictedSource = " + str(predicted_source[0]) + " WHERE CommandID = " + str(command_ids[i]) + " AND `Version` = " + str(args["version"]))


def get_category_shortcut(command_category):
    return ["SRD", "TD", "MD", "ND", "D", "MT", "MR", "NR", "Overall"][command_category]


def get_category_names():
    return ["Source, reference, direction", "Two directions", "More directions", "No direction", "Distance", "Block mentioned multiple times", "More references", "No reference", "Overall"]


def get_command_category(command, logo, benchmark):
    blocks, directions, distances = benchmark.get_blocks_and_directions(command, logo)

    if len(set(blocks)) < 2:
        return 7

    elif len(set(blocks)) > 2:
        return 6

    elif len(blocks) > 2:
        return 5

    elif len(distances) > 0:
        return 4

    elif len(directions) == 0:
        return 3

    elif len(directions) > 2:
        return 2

    elif len(directions) == 2:
        return 1

    elif len(directions) == 1:
        return 0
    
    else:
        assert False


def is_correct(predicted_location, gold_location):
    block_distance = 1.0936
    if abs(predicted_location[0] - gold_location[0]) <= 0.5 * block_distance and abs(predicted_location[1] - gold_location[1]) <= 0.5 * block_distance:
        return True
    return False


def analyze_model(run_id, dataset = None, print_bad_commands = True):
    args = load_args(run_id)
    model = load_model(args, run_id)

    if dataset == None:
        dataset = Dataset("dev", version = args["version"])
    
    benchmark = BenchmarkModel(version = args["version"], target = "source")

    categories = get_category_names()

    commands, worlds, sources, locations, tags, logos, source_flags = dataset.get_all_data()
    raw_commands, _, command_ids, _ = dataset.get_raw_commands_and_logos()
    predicted_sources, predicted_locations = model.predict(commands, worlds, sources, locations, tags, logos, source_flags, dataset.dataset_name)

    correct = []
    predictions = []
    command_by_category = []
    for i in range(len(categories)):
        predictions.append([])
        command_by_category.append([])
        correct.append(0)
    
    for i in range(0, len(commands)):
        category_index = get_command_category(commands[i], logos[i], benchmark)

        if predicted_sources is not None:
            if sources[i] == predicted_sources[i]:
                prediction = 1
            else:
                prediction = 0
                    
        if predicted_locations is not None:    
            prediction = distance.euclidean(predicted_locations[i], locations[i])
            if is_correct(predicted_locations[i], locations[i]):
                correct[category_index] += 1
                correct[-1] += 1

        predictions[category_index].append(prediction)
        predictions[-1].append(prediction)      #overall results

        command_by_category[category_index].append(command_ids[i])
        command_by_category[-1].append(command_ids[i])
                
    for i in range(len(categories)):
        mean = sum(predictions[i]) / len(predictions[i])
        
        if predicted_locations is not None:
            #correct_percentage = len([x for x in predictions[i] if x < 0.5]) / len(predictions[i])  #for location
            correct_percentage = correct[i] / len(predictions[i])
            bad_predictions = sorted(zip(predictions[i], command_by_category[i]), key = lambda x: x[0])[-5:] 
        
        else:
            bad_predictions = [x for x in zip(predictions[i], command_by_category[i]) if x[0] == 0][0:5]

        if predicted_sources is not None:
            print(categories[i] + " (" + str(len(predictions[i])) + "):\t" + str(mean))

        else:
            print(categories[i] + " (" + str(len(predictions[i])) + "):\t" + str(mean) + "\t" + str(correct_percentage))

        if print_bad_commands:
            for (bad_prediction, command_id) in bad_predictions:
                print(str(command_id) + ": " + str(bad_prediction))


def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument("--model", default="rnn", type=str, choices=["ffn", "rnn", "benchmark", "random_baseline", "deterministic_baseline"], help="Model to use")
    parser.add_argument("--max_epochs", default=1000, type=int, help="Maximum number of epochs")
    parser.add_argument("--batch_size", default=8, type=int, help="Batch size")
    parser.add_argument("--stop", default=20, type=int, help="Number of epochs without improvement before stopping training")
    parser.add_argument("--hidden_dimension", default=128, type=int, help="Number of neurons in last hidden layer")
    parser.add_argument("--threads", default=1, type=int, help="Maximum number of threads to use")
    parser.add_argument("--learning_rate", default=0.01, type=float, help="Learning rate")
    parser.add_argument("--rnn_cell_dim", default=128, type=int, help="Dimension of rnn cells.")
    parser.add_argument("--rnn_cell_type", default="LSTM", type=str, choices=["LSTM", "GRU"], help="Type of rnn cell")
    parser.add_argument("--bidirectional", default="True", type=str, choices=["False", "True"], help="Whether the RNN network is bidirectional")
    parser.add_argument("--target", default="location", type=str, choices=["source", "location"], help="Whether model should predict which block will be moved (source) or where it will be moved (location)")
    parser.add_argument("--test", default="False", type=str, choices=["False", "True"], help="Test trained model on testing data")
    parser.add_argument("--restore_and_test", default=-1, type=int, help="Load model with given id and test it on test data")
    parser.add_argument("--use_world", default="False", type=str, choices=["False", "True"], help="Whether model should use world state as input")
    parser.add_argument("--version", default=20, type=int, help="Which version of data to use")
    parser.add_argument("--dropout_input", default=0, type=float, help="Input dropout rate")
    parser.add_argument("--dropout_output", default=0, type=float, help="Output dropout rate")
    parser.add_argument("--embeddings", default="none", type=str, choices=["none", "random", "pretrained", "static_pretrained", "character", "character_variant"], help="Type of embeddings")
    parser.add_argument("--continue_training", default=-1, type=int, help="Load model with given ID and continue training")
    parser.add_argument("--create_images", default=-1, type=int, help="Load model with given id and create images based on models predictions")
    parser.add_argument("--use_tags", default="False", type=str, choices=["False", "True"], help="Whether use tags (Noun, Verb) as part of input to model")
    parser.add_argument("--rnn_output", default="direct_last_state", choices = ["last_state", "all_outputs", "direct_last_state"], type=str, help="How and what output of rnn will be used")
    parser.add_argument("--hidden_layers", default=2, type=int, help="Number of hidden layers in the middle part of network")
    parser.add_argument("--use_logos", default="False", type=str, choices=["False", "True"], help="Whether use logos as part of input to model")
    parser.add_argument("--seed", default=44, type=int, help="Random seed")
    parser.add_argument("--generated_commands", default=0, type=int, help="How many commands for training are automatically generated")
    parser.add_argument("--comment", default="", type=str, help="Description of this run")
    parser.add_argument("--run_id", default=-1, type=int, help="ID of this run for saving results in database")
    parser.add_argument("--distinct_x_y", default="False", type=str, choices=["False", "True"], help="Whether predict x and y coordinates of block together of distinctly.")
    parser.add_argument("--switch_blocks", default=0, type=float, help="Data augmentation - shuffling blocks in command and world")
    parser.add_argument("--source_flags", default="True", type=str, choices=["False", "True"], help="Use information which model is source when predicting location")
    parser.add_argument("--analyze", default=-1, type=int, help="Run_ID of model which you want analyze")
    parser.add_argument("--gradient_clipping", default="False", type=str, choices = ["False", "True"], help="Whether gradient clipping should be used")
    parser.add_argument("--optimizer_type", default="Adam", type=str, choices = ["Adam", "SGD", "Adam_exponential_decay", "SGD_exponential_decay", "Adam_variable_decay", "SGD_variable_decay"], help="Optimization algorithm and scheme of decreasing learning rate (default is no decreasing)")


    args = parser.parse_args()
    args = vars(args)

    bool_args = ["bidirectional", "test", "use_world", "use_tags", "use_logos", "distinct_x_y", "source_flags", "gradient_clipping"]

    for bool_arg in bool_args:
        if args[bool_arg] == "False":
            args[bool_arg] = False
        elif args[bool_arg] == "True":
            args[bool_arg] = True
        else:
            assert False

    return args


def main():
    args = parse_arguments()
    random.seed(args["seed"])
    
    if args["restore_and_test"] != -1:
        test_model(args["restore_and_test"])
        return

    if args["create_images"] != -1:
        create_images(args["create_images"])
        return

    if args["analyze"] != -1:
        analyze_model(args["analyze"], Dataset("test", 20))
        return 

    if args["continue_training"] == -1:
        if args["run_id"] == -1:
            run_id = get_run_id()
            args["run_id"] = run_id
        else:
            run_id = args["run_id"]

        if args["model"] in ["rnn", "ffn"]:
            model = Network(args["model"], hidden_dimension = args["hidden_dimension"], run_id = run_id, initial_learning_rate = args["learning_rate"], target = args["target"],
                            rnn_cell_dim = args["rnn_cell_dim"], rnn_cell_type = args["rnn_cell_type"], bidirectional = args["bidirectional"], threads = args["threads"], use_world = args["use_world"],
                            dropout_input = args["dropout_input"], dropout_output = args["dropout_output"], embeddings = args["embeddings"], version = args["version"], use_tags = args["use_tags"],
                            rnn_output = args["rnn_output"], hidden_layers = args["hidden_layers"], use_logos = args["use_logos"], use_source_flags = args["source_flags"], 
                            distinct_x_y = args["distinct_x_y"], seed = args["seed"], optimizer_type = args["optimizer_type"], gradient_clipping = args["gradient_clipping"])

        elif args["model"] in ["benchmark"]:
            model = BenchmarkModel(args["version"], target = args["target"])

        elif args["model"] in ["random_baseline"]:
            model = RandomBaseline(target = args["target"])

        elif args["model"] in ["deterministic_baseline"]:
            model = DeterministicBaseline(target = args["target"])


    else:
        run_id = args["continue_training"]
        args["run_id"] = run_id
        if args["run_id"] != -1:
            print("Warning run_id argument ignored")
        user_args = copy.deepcopy(args)
        args = load_args(run_id)
        args["stop"] = user_args["stop"]
        args["max_epochs"] = user_args["max_epochs"]
        args["test"] = user_args["test"]
        model = load_model(args, run_id)
        #best_result = load_best_result(run_id)
        #starting_epoch = best_result[3]

    train(run_id, model, args)


def train(run_id, model, args):
    
    start_time = time.time()
    
    epochs_without_improvement = 0
    best_results = load_best_result(run_id)
    starting_epoch = best_results[-1]

    train_data = Dataset("train", args["version"], generated_commands=args["generated_commands"], switch_blocks = args["switch_blocks"])
    dev_data = Dataset("dev", args["version"])
    test_data = Dataset("test", args["version"])

    variable_learning_rate = args["learning_rate"]

    for epoch in range(starting_epoch, args["max_epochs"]):
        train_data.next_epoch()
        
        while not train_data.epoch_end():
            commands, worlds, sources, locations, tags, logos, source_flags = train_data.get_next_batch(args["batch_size"])
            model.train(commands, worlds, sources, locations, tags, logos, source_flags, variable_learning_rate)

        current_results = evaluate(model, dev_data, epoch)
        
        print_results(current_results)
        
        if improvement(best_results, current_results):
            best_results = current_results
            epochs_without_improvement = 0
            if args["model"] in ["rnn", "fnn"]:
                run_dir = "checkpoints/" + str(run_id)
                if not os.path.isdir(run_dir):
                    os.makedirs(run_dir)
                model.saver.save(model.session, run_dir + "/best.ckpt")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement == args["stop"]:
               break

            if epochs_without_improvement % 10 == 0:
                variable_learning_rate = variable_learning_rate / 4.0
    
    print("Best result:")
    print_results(best_results)

    if args["test"]:
        if args["model"] in ["rnn", "fnn"]:
            best_net = tf.train.get_checkpoint_state("checkpoints/" + str(run_id))
            model.saver.restore(model.session, best_net.model_checkpoint_path)
        
        test_results = evaluate(model, test_data, best_results[2])

        print("Test results:")
        print_results(test_results)
    else:
        test_results = (None, None, None, None)

    save(run_id, args, best_results, test_results, start_time)
    print(args["comment"])


if __name__ == "__main__":
    main()       
            
 
