import math
import sys

import numpy
import numpy as np
import stormpy
import stormpy.examples
import stormpy.examples.files

import observations


def model_from_sparse_matrix(trans_matrix: stormpy.SparseMatrix, labels: stormpy.StateLabeling = None) -> stormpy.SparseDtmc:
    """
    Creates a DTMC model from a given transition matrix.

    :param values: Value array (Number of Non-Zero elements)
    :param col: Col array (Number of Non-Zero elements)
    :param row: Row array (Number of states elements + 1)
    :param labels: Dictionary of String -> BitVector used to assign label to each state
    """
    N_states = trans_matrix.nr_rows

    if labels is None:
        labeling = stormpy.storage.StateLabeling(N_states)
    else:
        labeling = labels

    components = stormpy.SparseModelComponents(transition_matrix=trans_matrix)
    components.state_labeling = labeling
    dtmc = stormpy.storage.SparseDtmc(components)
    return dtmc


def frequentist(sample: np.ndarray, model: stormpy.SparseDtmc, smoothing: float = 0) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Learn the probabilities of a model using the frequentist way.

    When out of N samples we observe P times successor state si, we estimate:
    P(s0, a, si) ~= P/N

    :param smoothing: Laplace smoothing parameter to avoid skipping potential transitions that would just not be in
    the sample.
    :param sample: List of random observations on the model
    :param model: DTMC model which we want to learn the transition probabilities.
    """
    n_states = len(model.states)
    n = np.zeros(n_states)
    nb_trans = [len(s.actions[0].transitions) for s in model.states]
    row = np.zeros(n_states + 1, numpy.int8)
    for s in range(n_states):
        row[s + 1] = row[s] + nb_trans[s]

    col = []
    for s in model.states:
        for t in s.actions[0].transitions:
            col.append(t.column)
    col = np.array(col)

    values = np.zeros(np.sum(nb_trans))

    for (start, dest) in sample:
        n[start] += 1
        i = row[start]
        for j in range(i, row[start + 1]):
            if col[j] == dest:
                values[j] += 1

    builder = stormpy.SparseMatrixBuilder(rows=n_states, columns=n_states)
    for s in range(n_states):
        for i in range(row[s], row[s + 1]):
            values[i] = (values[i] + smoothing) / (n[s] + nb_trans[s] * smoothing)
            c = col[i]
            v = values[i]
            builder.add_next_value(s, c, v)

    return builder.build()


def bayesian_dirichlet(sample: np.ndarray, model: stormpy.SparseDtmc):
    """
    Estimates the transition probabilities using a dirichlet distribution via MAP-estimation.
    :param sample: List of random observations on the model
    :param model: Model whose transitions must be estimated
    """
    n_states = model.nr_states
    m = model.nr_transitions
    nb_trans = [len(s.actions[0].transitions) for s in model.states]
    row = np.zeros(n_states + 1, numpy.int8)
    for s in range(n_states):
        row[s + 1] = row[s] + nb_trans[s]

    col = []
    for s in model.states:
        for t in s.actions[0].transitions:
            col.append(t.column)
    col = np.array(col)

    values = np.zeros(np.sum(nb_trans))
    a = np.ones(m)
    k = np.zeros([m, m])

    # Count N and k's values
    for (start, dest) in sample:
        i = row[start]
        for j in range(i, row[start + 1]):
            if col[j] == dest:
                k[i,j] += 1

    # Updates alpha (a) by adding k's values to it.
    for elem in k:
        a += elem

    # estimate p with the mode
    builder = stormpy.SparseMatrixBuilder(rows=n_states, columns=n_states)
    for s in range(n_states):
        for i in range(row[s], row[s + 1]):
            values[i] = (a[i] - 1) / (sum(a) - m)
            c = col[i]
            v = values[i]
            builder.add_next_value(s, c, v)

    return builder.build()


if __name__ == "__main__":
    program = stormpy.parse_prism_program(stormpy.examples.files.prism_dtmc_die)
    model = stormpy.build_model(program)

    obs = observations.parse_observations(observations.DEFAULT_PATH)

    properties_raw = [
        'P=? [F "one"]',
        'P=? [F "two"]',
        'P=? [F "three"]',
        'P=? [F "one" | "two" | "three"]',
    ]

    properties = stormpy.parse_properties(';'.join(properties_raw))
    m = None

    if len(sys.argv) > 1:
        method = sys.argv[1]
        if method == "frequentist":
            matrix = frequentist(obs, model)
            m = model_from_sparse_matrix(matrix, model.labeling)

            for state in m.states:
                for action in state.actions:
                    for transition in action.transitions:
                        print(f"{state.id}, {state.labels}, {transition.value()}, {transition.column}")
        elif method == "bayesian":
            matrix = bayesian_dirichlet(obs, model)
            m = model_from_sparse_matrix(matrix, model.labeling)

            for state in m.states:
                for action in state.actions:
                    for transition in action.transitions:
                        print(f"{state.id}, {state.labels}, {transition.value()}, {transition.column}")

        for p in range(len(properties)):
            result_base = stormpy.model_checking(model, properties[p])
            result_base_vector = [x for x in result_base.get_values()]

            result_predict = stormpy.model_checking(m, properties[p])
            result_predict_vector = [x for x in result_predict.get_values()]

            print(f"{p} : \n\tBase:\t{result_base_vector}\n\tPrediction:\t\t{result_predict_vector}")

