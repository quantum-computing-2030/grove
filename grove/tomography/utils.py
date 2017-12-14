##############################################################################
# Copyright 2017-2018 Rigetti Computing
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
##############################################################################

"""
Utilities for encapsulating bases and properties of quantum operators and super-operators
as represented by qutip.Qobj()'s.
"""

import itertools
import logging
from itertools import product as cartesian_product

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import qutip as qt
import tqdm
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.mplot3d import Axes3D
from pyquil.gates import I, X, H, CZ
from pyquil.quil import Program

from grove.tomography.operator_utils import OperatorBasis

try:
    # Python 2
    from itertools import izip
except ImportError:
    # Python 3
    izip = zip

_log = logging.getLogger(__name__)

THREE_COLOR_MAP = ['#48737F', '#FFFFFF', '#D6619E']
rigetti_3_color_cm = LinearSegmentedColormap.from_list("Rigetti", THREE_COLOR_MAP[::-1], N=100)

FIVE_COLOR_MAP = ['#C671A2', '#545253', '#85B5BE', '#ECE9CC', '#C671A2']
rigetti_4_color_cm = LinearSegmentedColormap.from_list("Rigetti", FIVE_COLOR_MAP[::-1], N=100)
EPS = 1e-2
SEED = 137
BELL_STATE_PROGRAM = Program([H(0), H(1), CZ(0, 1), H(1)])
CNOT_PROGRAM = Program([H(1), CZ(0, 1), H(1)])

BAD_1Q_READOUT = np.array([[.9, .15],
                           [.1, .85]])
BAD_2Q_READOUT = np.kron(BAD_1Q_READOUT, BAD_1Q_READOUT)


QX = qt.sigmax()
QY = qt.sigmay()
QZ = qt.sigmaz()
QI = qt.qeye(2)

# constants to provide optional fancy progress bars
NOTEBOOK_MODE = False
TRANGE = tqdm.trange


def notebook_mode(m):
    """
    Configure whether this module should assume that it is being run from a jupyter notebook.
    This sets some global variables related to how progress for long measurement sequences is
    indicated.

    :param bool m: If True, assume to be in notebook.
    :return: None
    :rtype: NoneType
    """
    global NOTEBOOK_MODE
    global TRANGE
    NOTEBOOK_MODE = m
    if NOTEBOOK_MODE:
        TRANGE = tqdm.tnrange
    else:
        TRANGE = tqdm.trange


def to_density_matrix(state):
    """
    Convert a Hilbert space vector to a density matrix.

    :param qt.basis state: The state to convert into a density matrix.
    :return: The density operator corresponding to state.
    :rtype: qutip.qobj.Qobj
    """
    return state * state.dag()


GS = to_density_matrix(qt.basis(2, 0))
ES = to_density_matrix(qt.basis(2, 1))

# using the Pi-basis for POVM terms allows to easily associate the preparations with individual
# multi-qubit projectors
POVM_PI_BASIS = OperatorBasis([("0", GS), ("1", ES)])
PAULI_BASIS = OperatorBasis(
    [("I", QI / np.sqrt(2)), ("X", QX / np.sqrt(2)),
     ("Y", QY / np.sqrt(2)), ("Z", QZ / np.sqrt(2))])


def n_qubit_pauli_basis(n):
    """
    Construct the tensor product operator basis of `n` PAULI_BASIS's.

    :param int n: The number of qubits.
    :return: The product Pauli operator basis of `n` qubits
    :rtype: OperatorBasis
    """
    if n >= 1:
        return PAULI_BASIS ** n
    else:  # pragma no coverage
        raise ValueError("n = {} should be at least 1.".format(n))


def n_qubit_ground_state(n):
    """
    Construct the tensor product of `n` ground states |0>.

    :param int n: The number of qubits.
    :return: The state |000...0> for `n` qubits.
    :rtype: qutip.Qobj
    """
    return qt.tensor(*([GS] * n))


def sample_outcomes(probs, n):
    """
    For a discrete probability distribution ``probs`` with outcomes 0, 1, ..., k-1 draw ``n``
    random samples.

    :param list probs: A list of probabilities.
    :param Number n: The number of random samples to draw.
    :return: An array of samples drawn from distribution probs over 0, ..., len(probs) - 1
    :rtype: numpy.ndarray
    """
    dist = np.cumsum(probs)
    rs = np.random.rand(n)
    return np.array([(np.where(r < dist)[0][0]) for r in rs])


def basis_state_preps(*qubits):
    """
    Generate a sequence of programs that prepares the measurement
    basis states of some set of qubits in the order such that the qubit
    with highest index is iterated over the most quickly:
    E.g., for qubits=(0, 1), it returns the circuits::

        I_0 I_1
        I_0 X_1
        X_0 I_1
        X_0 X_1
    :param list qubits: Each qubit to include in the basis state preparation.
    :return: Yields programs for each basis state preparation.
    :rtype: Program
    """
    for prep in cartesian_product([I, X], repeat=len(qubits)):
        basis_prep = Program()
        for gate, qubit in zip(prep, qubits):
            basis_prep.inst(gate(qubit))
        yield basis_prep


def basis_labels(n):
    """
    Generate a list of basis labels for `n` qubits, ordered from least to greatest, in big-endian
     format:

        ['00..00', '00..01', ..., '11..11']

    :param n:
    :return: A list of strings of length n that enumerate the n-qubit bitstrings
    :rtype: list
    """
    return ["".join(labels) for labels in itertools.product('01', repeat=n)]


def sample_bad_readout(program, num_samples, assignment_probs, cxn):
    """
    Generate `n` samples of measuring all outcomes of a Quil `program`
    assuming the assignment probabilities `assignment_probs` by simulating the
    wave function on a qvm QVMConnection `cxn`

    :param pyquil.quil.Program program: The program.
    :param int num_samples: The number of samples
    :param numpy.ndarray assignment_probs: A matrix of assignment probabilities
    :param QVMConnection cxn: the QVM connection.
    :return: The resulting sampled outcomes from assignment_probs applied to cxn, one dimensional.
    :rtype: numpy.ndarray
    """
    wf = cxn.wavefunction(program)
    return sample_outcomes(assignment_probs.dot(abs(wf.amplitudes.ravel())**2), num_samples)


def make_histogram(samples, ksup):
    """
    For a list of samples [s1, s2, ..., sN] taking on integer values from 0 to ksup-1,
    make a histogram of each integer's outcome and return it.

    :param samples: The samples.
    :param ksup: The (exclusive) upper bound
    :return: A histogram of outcomes.
    :rtype: numpy.ndarray
    """
    return np.histogram(samples, np.arange(ksup + 1) - 0.5)[0]


def estimate_assignment_probs(bitstring_prep_histograms):
    """
    Compute the estimated assignment probability matrix for a sequence of single shot histograms
    obtained by running the programs generated by `basis_state_preps()`.

        bitstring_prep_histograms[i,j] = #number of measured outcomes j when running program i

    The assignment probability is obtained by transposing and afterwards normalizing the columns.

        p[j, i] = Probability to measure outcome j when preparing the state with program i.

    :param list|numpy.ndarray bitstring_prep_histograms: A nested list or 2d array with shape
    (d, d), where ``d = 2**nqubits`` is the dimension of the Hilbert space. The first axis varies
    over the state preparation program index, the second axis corresponds to the measured bitstring.
    :return: The assignment probability matrix.
    :rtype: numpy.ndarray
    """
    p = np.array(bitstring_prep_histograms, dtype=float).T
    p /= p.sum(axis=0)[np.newaxis, :]
    return p


def plot_pauli_transfer_matrix(ptransfermatrix, ax, labels, title):
    """
    Visualize the Pauli Transfer Matrix of a process.

    :param numpy.ndarray ptransfermatrix: The Pauli Transfer Matrix
    :param ax: The matplotlib axes.
    :param labels: The labels for the operator basis states.
    :param title: The title for the plot
    :return: The modified axis object.
    :rtype: AxesSubplot

    """
    im = ax.imshow(ptransfermatrix, interpolation="nearest", cmap=rigetti_3_color_cm, vmin=-1,
                   vmax=1)
    dim = len(labels)
    plt.colorbar(im, ax=ax)
    ax.set_xticks(range(dim))
    ax.set_xlabel("Input Pauli Operator", fontsize=20)
    ax.set_yticks(range(dim))
    ax.set_ylabel("Output Pauli Operator", fontsize=20)
    ax.set_title(title, fontsize=25)
    ax.set_xticklabels(labels, rotation=45)
    ax.set_yticklabels(labels)
    ax.grid(False)
    return ax


def generated_states(initial_state, preparations):
    """
    Generate states prepared from channel operators acting on an initial state.
    Typically the channel operators will be unitary.

    :param qutip.Qobj initial_state: The initial state as a density matrix.
    :param (list|tuple) preparations: The unitary channel operators that transform the initial
     state.
    :return: The states generated from preparations acting on intial_state
    :rtype: list
    """
    return [e * initial_state * e.dag() for e in preparations]


def state_histogram(rho, ax=None, title="", threshold=0.001):
    """
    Visualize a density matrix as a 3d bar plot with complex phase encoded
    as the bar color.

    This code is a modified version of an equivalent function in qutip which is
    released under the (New) BSD license
    http://qutip.org/docs/3.1.0/apidoc/functions.html#qutip.visualization.matrix_histogram_complex


    :param qutip.Qobj rho: The density matrix.
    :param Axes3D ax: The axes object.
    :param str title: The axes title.
    :param float threshold: (Optional) minimum magnitude of matrix elements. Values below this
    are hidden.
    :return: The axis
    :rtype: mpl_toolkits.mplot3d.Axes3D
    """
    rho_amps = rho.data.toarray().ravel()
    nqc = int(round(np.log2(rho.shape[0])))
    if ax is None:
        fig = plt.figure(figsize=(10, 6))
        ax = Axes3D(fig, azim=-35, elev=35)
    cmap = rigetti_4_color_cm
    norm = mpl.colors.Normalize(-np.pi, np.pi)
    colors = cmap(norm(np.angle(rho_amps)))
    dzs = abs(rho_amps)
    colors[:, 3] = 1.0 * (dzs > threshold)
    xs, ys = np.meshgrid(range(2 ** nqc), range(2 ** nqc))
    xs = xs.ravel()
    ys = ys.ravel()
    zs = np.zeros_like(xs)
    dxs = dys = np.ones_like(xs) * 0.8

    _ = ax.bar3d(xs, ys, zs, dxs, dys, dzs, color=colors)
    ax.set_xticks(np.arange(2 ** nqc) + .4)
    ax.set_xticklabels(basis_labels(nqc))
    ax.set_yticks(np.arange(2 ** nqc) + .4)
    ax.set_yticklabels(basis_labels(nqc))
    ax.set_zlim3d([0, 1])

    cax, kw = mpl.colorbar.make_axes(ax, shrink=.75, pad=.1)
    cb = mpl.colorbar.ColorbarBase(cax, cmap=cmap, norm=norm)
    cb.set_ticks([-np.pi, -np.pi / 2, 0, np.pi / 2, np.pi])
    cb.set_ticklabels((r'$-\pi$', r'$-\pi/2$', r'$0$', r'$\pi/2$', r'$\pi$'))
    cb.set_label('arg')
    ax.view_init(azim=-55, elev=45)
    ax.set_title(title)
    return ax


def bitlist_to_int(bitlist):
    """Convert a binary bitstring into the corresponding unsigned integer.

    :param list bitlist: A list of ones of zeros.
    :return: The corresponding integer.
    :rtype: int
    """

    ret = 0
    for b in bitlist:
        ret = (ret << 1) | (int(b) & 1)
    return ret


def sample_assignment_probs(qubits, nsamples, cxn):
    """
    Sample the assignment probabilities of qubits using nsamples per measurement, and then compute
    the estimated assignment probability matrix. See the docstring for estimate_assignment_probs for
    more information.

    :param list qubits: Qubits to sample the assignment probabilities for.
    :param int nsamples: The number of samples to use in each measurement.
    :param QPUConnection|QVMConnection cxn: The Connection object to connect to Forest.
    :return: The assignment probability matrix.
    :rtype: numpy.ndarray
    """
    num_qubits = len(qubits)
    dimension = 2 ** num_qubits
    hists = []
    preps = basis_state_preps(*qubits)
    for jj, p in izip(TRANGE(dimension), preps):
        results = cxn.run_and_measure(p, qubits, nsamples)
        idxs = list(map(bitlist_to_int, results))
        hists.append(make_histogram(idxs, dimension))
    return estimate_assignment_probs(hists)
