import csv
import random

import numpy as np
from scipy.constants import speed_of_light


class Sensor:
    """Common base class for sensor & assoc methods"""

    def __init__(self):
        pass

    def observation(self, state):
        """Undefined observation sample method"""
        pass

    def weight(self, hyp, obs, state):
        """Undefined method for importance
        weight of a state given observation
        """
        pass

    def acceptance(self, state):
        """Undefined method for defining
        detector acceptance pattern
        """
        pass


def get_radiation_pattern(antenna_filename=None):
    radiation_pattern = []
    with open(antenna_filename, newline="", encoding="UTF-8") as csvfile:
        reader = csv.reader(csvfile, delimiter="\n")
        for row in reader:
            radiation_pattern.append(float(row[0]))

    def shift(seq, n):
        return seq[n:] + seq[:n]

    radiation_pattern = shift(radiation_pattern, 90)

    return radiation_pattern


def get_directivity(radiation_pattern, theta):
    return radiation_pattern[int(theta * 180 / np.pi) % len(radiation_pattern)]


def rssi(
    distance,
    directivity_rx,
    power_tx=26,
    directivity_tx=1,
    freq=5.7e9,
    fading_sigma=None,
):
    """
    Calculate the received signal strength at a receiver in dB
    """
    power_rx = (
        float(power_tx)
        + directivity_rx
        + float(directivity_tx)
        + (20 * np.log10(speed_of_light / (4 * np.pi)))
        + -20 * np.log10(distance)
        + -20 * np.log10(float(freq))
    )
    # fading
    if fading_sigma:
        power_rx -= np.random.normal(0, fading_sigma)
    return power_rx


def dist_from_rssi(rssi_val, directivity_rx, power_tx=10, directivity_tx=1, freq=2.4e9):
    """
    Calculate distance between receiver and transmitter based on RSSI.
    """
    distance = 10 ^ (
        (
            power_tx
            + directivity_rx
            + directivity_tx
            - rssi_val
            - (20 * np.log10(freq))
            + (20 * np.log10(speed_of_light / (4 * np.pi)))
        )
        / 20
    )
    return distance


def dB_to_power(dB):
    return 10 ** (dB / 10)


def power_to_dB(power):
    return 10 * np.log10(power)


class DoubleRSSILofi(Sensor):
    """
    Uses RSSI comparison from two opposite facing Yagi/directional antennas
    """

    def __init__(
        self,
        antenna_filename=None,
        power_tx=26,
        directivity_tx=1,
        freq=5.7e9,
        fading_sigma=None,
    ):
        self.radiation_pattern = get_radiation_pattern(
            antenna_filename=antenna_filename
        )
        self.std_dev = 6
        self.power_tx = power_tx
        self.directivity_tx = directivity_tx
        self.freq = freq
        self.fading_sigma = fading_sigma
        if self.fading_sigma:
            self.fading_sigma = float(self.fading_sigma)

    def weight(self, hyp, obs):
        # TODO add front, mid, back
        # expected_rssi = hyp # array [# of particles x 2 rssi readings(front rssi & back rssi)]
        expected_rssi = hyp
        observed_rssi = obs[0]
        expected_diff = expected_rssi[:, 0] - expected_rssi[:, 1]
        observed_diff = observed_rssi[0] - observed_rssi[1]

        # Gaussian weighting function
        numerator = np.power(expected_diff - observed_diff, 2.0)
        denominator = 2 * np.power(self.std_dev, 2.0)
        weight = np.exp(-numerator / denominator)  # + 0.000000001
        # likelihood = np.prod(weight, axis=1)
        return weight

    def weight3(self, hyp, obs):
        # TODO add front, mid, back
        # expected_rssi = hyp # array [# of particles x 2 rssi readings(front rssi & back rssi)]
        expected_rssi = hyp
        observed_rssi = obs[0]

        multiplier = 1
        expected_diff = multiplier * (expected_rssi[:, 0] - expected_rssi[:, 1])
        observed_diff = multiplier * (observed_rssi[0] - observed_rssi[1])
        print("std = ", np.std(expected_diff))
        lofi_sigma = 0.7 * np.std(expected_diff)
        # Gaussian weighting function
        numerator = np.power(expected_diff - observed_diff, 2.0)
        print("numerator = ", numerator)
        denominator = 2 * np.power(lofi_sigma, 2.0)
        print("denominator = ", denominator)
        weight = np.exp(-numerator / denominator) + 0.001
        # likelihood = np.prod(weight, axis=1)
        print("expect = ", expected_diff)
        print("obs = ", observed_diff)
        print("observed = ", observed_rssi)
        print("weight = ", weight)
        return weight

    def weight2(self, hyp, obs):
        # TODO add front, mid, back
        # expected_rssi = hyp # array [# of particles x 2 rssi readings(front rssi & back rssi)]
        expected_rssi = hyp
        lofi_sigma = 1e-8  # 5
        expected_diff = expected_rssi[:, 0] - expected_rssi[:, 1]
        observed_rssi = obs[0]
        observed_diff = observed_rssi[0] - observed_rssi[1]
        expected_front_greater = expected_diff > lofi_sigma
        expected_unsure = np.abs(expected_diff) <= lofi_sigma
        expected_back_greater = expected_diff < (-1 * lofi_sigma)

        observed_front_greater = observed_diff > lofi_sigma
        observed_unsure = np.abs(observed_diff) <= lofi_sigma
        observed_back_greater = observed_diff < (-1 * lofi_sigma)
        if observed_front_greater:
            match = (0.9 ** (1 / 2)) * expected_front_greater
            unsure = (0.5 ** (1 / 2)) * expected_unsure
            no_match = (0.1 ** (1 / 2)) * expected_back_greater
            likelihood = match + unsure + no_match
        elif observed_unsure:
            match = (0.90 ** (1 / 2)) * expected_unsure
            unsure = (0.10 ** (1 / 2)) * expected_front_greater
            no_match = (0.10 ** (1 / 2)) * expected_back_greater
            likelihood = match + unsure + no_match
        elif observed_back_greater:
            match = (0.9 ** (1 / 2)) * expected_back_greater
            unsure = (0.5 ** (1 / 2)) * expected_unsure
            no_match = (0.1 ** (1 / 2)) * expected_front_greater
            likelihood = match + unsure + no_match
        return likelihood

    # samples observation given state
    def observation(self, state):
        # Calculate observation for multiple targets
        power_front = 0
        power_back = 0
        for ts in state:  # target_state, particle_state
            distance = ts[0]
            theta_front = ts[1] * np.pi / 180.0
            theta_back = theta_front + np.pi
            directivity_rx_front = get_directivity(self.radiation_pattern, theta_front)
            directivity_rx_back = get_directivity(self.radiation_pattern, theta_back)
            power_front += dB_to_power(
                rssi(
                    distance,
                    directivity_rx_front,
                    power_tx=self.power_tx,
                    directivity_tx=self.directivity_tx,
                    freq=self.freq,
                    fading_sigma=self.fading_sigma,
                )
            )
            power_back += dB_to_power(
                rssi(
                    distance,
                    directivity_rx_back,
                    power_tx=self.power_tx,
                    directivity_tx=self.directivity_tx,
                    freq=self.freq,
                    fading_sigma=self.fading_sigma,
                )
            )
        rssi_front = power_to_dB(power_front)
        rssi_back = power_to_dB(power_back)

        return [rssi_front, rssi_back]


class SingleRSSI(Sensor):
    """
    Uses RSSI comparison from two opposite facing Yagi/directional antennas
    """

    def __init__(
        self,
        antenna_filename=None,
        power_tx=26,
        directivity_tx=1,
        freq=5.7e9,
        fading_sigma=None,
    ):
        self.radiation_pattern = get_radiation_pattern(
            antenna_filename=antenna_filename
        )
        self.std_dev = 15

        self.power_tx = power_tx
        self.directivity_tx = directivity_tx
        self.freq = freq

        self.fading_sigma = fading_sigma
        if self.fading_sigma:
            self.fading_sigma = float(self.fading_sigma)

    def weight(self, hyp, obs):
        # array [# of particles x 2 rssi readings(front rssi & back rssi)]
        expected_rssi = hyp
        observed_rssi = obs
        # Gaussian weighting function
        numerator = np.power(expected_rssi - observed_rssi, 2.0)
        denominator = 2 * np.power(self.std_dev, 2.0)
        weight = np.exp(-numerator / denominator)  # + 0.000000001
        likelihood = np.prod(weight, axis=1)
        return likelihood

    # samples observation given state
    def observation(self, state):
        # Calculate observation for multiple targets
        power_front = 0

        for ts in state:  # target_state, particle_state
            distance = ts[0]
            theta_front = ts[1] * np.pi / 180.0
            directivity_rx_front = get_directivity(self.radiation_pattern, theta_front)
            power_front += dB_to_power(
                rssi(
                    distance,
                    directivity_rx_front,
                    power_tx=self.power_tx,
                    directivity_tx=self.directivity_tx,
                    freq=self.freq,
                    fading_sigma=self.fading_sigma,
                )
            )
        rssi_front = power_to_dB(power_front)
        return [rssi_front]


class DoubleRSSI(Sensor):
    """
    Uses RSSI comparison from two opposite facing Yagi/directional antennas
    """

    def __init__(
        self,
        antenna_filename=None,
        power_tx=26,
        directivity_tx=1,
        freq=5.7e9,
        fading_sigma=None,
    ):
        self.radiation_pattern = get_radiation_pattern(
            antenna_filename=antenna_filename
        )
        self.std_dev = 15
        self.power_tx = power_tx
        self.directivity_tx = directivity_tx
        self.freq = freq
        self.fading_sigma = fading_sigma
        if self.fading_sigma:
            self.fading_sigma = float(self.fading_sigma)

    def weight(self, hyp, obs):
        # array [# of particles x 2 rssi readings(front rssi & back rssi)]
        expected_rssi = hyp
        observed_rssi = obs
        # Gaussian weighting function
        numerator = np.power(expected_rssi - observed_rssi, 2.0)
        denominator = 2 * np.power(self.std_dev, 2.0)
        weight = np.exp(-numerator / denominator)  # + 0.000000001
        likelihood = np.prod(weight, axis=1)
        return likelihood

    # samples observation given state
    def observation(self, state):
        power_front = 0
        power_back = 0
        for ts in state:  # target_state, particle_state
            distance = ts[0]
            theta_front = ts[1] * np.pi / 180.0
            theta_back = theta_front + np.pi
            directivity_rx_front = get_directivity(self.radiation_pattern, theta_front)
            directivity_rx_back = get_directivity(self.radiation_pattern, theta_back)
            power_front += dB_to_power(
                rssi(
                    distance,
                    directivity_rx_front,
                    power_tx=self.power_tx,
                    directivity_tx=self.directivity_tx,
                    freq=self.freq,
                    fading_sigma=self.fading_sigma,
                )
            )
            power_back += dB_to_power(
                rssi(
                    distance,
                    directivity_rx_back,
                    power_tx=self.power_tx,
                    directivity_tx=self.directivity_tx,
                    freq=self.freq,
                    fading_sigma=self.fading_sigma,
                )
            )
        rssi_front = power_to_dB(power_front)
        rssi_back = power_to_dB(power_back)
        return [rssi_front, rssi_back]


class SignalStrength(Sensor):
    """
    Uses signal strength as observation
    """

    def __init__(self):
        self.num_avail_obs = 1
        self.std_dev = 10

    def weight(self, hyp, obs, state):
        expected_r = state[0]
        obs_r = np.sqrt(1 / obs[0][0])
        # Gaussian weighting function
        numer_fact = np.power(expected_r - obs_r, 2.0)
        denom_fact = 2 * np.power(self.std_dev, 2.0)
        weight = np.exp(-numer_fact / denom_fact) + 0.000000001
        return weight

    # samples observation given state
    def observation(self, state):
        return 1 / ((np.random.normal(state[0], self.std_dev)) ** 2)


class Drone(Sensor):
    """Drone sensor"""

    def __init__(self):
        self.num_avail_obs = 2

    # importance weight of state given observation
    def weight(self, hyp, obs, state):

        # Get acceptance value for state value
        obs_weight = self.acceptance(state)

        # Convolve acceptance with observation weight
        if obs == 1:
            obs_weight *= self.obs1_prob(state)
        elif obs == 0:
            obs_weight *= 1 - self.obs1_prob(state)
        else:
            raise ValueError(
                f"Observation number ({obs}) outside acceptable int values: 0-{self.num_avail_obs-1}"
            )

        return obs_weight

    def acceptance(self, state):
        return 1.0

    # samples observation given state
    def observation(self, state):

        obs1_val = self.obs1_prob(state)
        weights = [1.0 - obs1_val, obs1_val]
        obsers = [0, 1]
        return random.choices(obsers, weights)[0]

    # probability of observation 1
    def obs1_prob(self, state):
        rel_heading = state[1]
        if -60 <= rel_heading <= 60:
            return 0.9
        if 120 <= rel_heading <= 240:
            return 0.1
        return 0.5


class Heading(Sensor):
    def __init__(self, sensor_range=150):
        self.sensor_range = sensor_range
        self.num_avail_obs = 4

    # importance weight of state given observation
    def weight(self, hyp, obs, state):

        # Get acceptance value for state value
        obs_weight = self.acceptance(state)

        # Convolve acceptance with observation weight
        if obs == 0:
            obs_weight *= self.obs0(state)
        elif obs == 1:
            obs_weight *= self.obs1(state)
        elif obs == 2:
            obs_weight *= self.obs2(state)
        elif obs == 3:
            obs_weight *= self.obs3(state)
        else:
            raise ValueError(
                f"Observation number ({obs}) outside acceptable int values: 0-{self.num_avail_obs-1}"
            )

        return obs_weight

    def acceptance(self, state):
        return 1.0

    def observation(self, state):
        """
        Samples observation given state
        """
        weights = [
            self.obs0(state),
            self.obs1(state),
            self.obs2(state),
            self.obs3(state),
        ]
        obsers = [0, 1, 2, 3]
        return random.choices(obsers, weights)[0]

    def obs1(self, state):
        # rel_brg = state[1] - state[3]
        rel_brg = state[1]
        state_range = state[0]
        if rel_brg < 0:
            rel_brg += 360
        if ((60 < rel_brg < 90) or (270 < rel_brg < 300)) and (
            state_range < self.sensor_range / 2
        ):
            return 1
        if ((60 < rel_brg < 90) or (270 < rel_brg < 300)) and (
            state_range < self.sensor_range
        ):
            return 2 - 2 * state_range / self.sensor_range
        return 0.0001

    def obs2(self, state):
        # rel_brg = state[1] - state[3]
        rel_brg = state[2]
        state_range = state[1]
        if rel_brg < 0:
            rel_brg += 360
        if ((90 <= rel_brg < 120) or (240 < rel_brg <= 270)) and (
            state_range < self.sensor_range / 2
        ):
            return 1
        if ((90 <= rel_brg < 120) or (240 < rel_brg <= 270)) and (
            state_range < self.sensor_range
        ):
            return 2 - 2 * state_range / self.sensor_range
        return 0.0001

    def obs3(self, state):
        # rel_brg = state[1] - state[3]
        rel_brg = state[1]
        state_range = state[0]
        if rel_brg < 0:
            rel_brg += 360
        if (120 <= rel_brg <= 240) and (state_range < self.sensor_range / 2):
            return 1
        if (120 <= rel_brg <= 240) and (state_range < self.sensor_range):
            return 2 - 2 * state_range / self.sensor_range
        return 0.0001

    def obs0(self, state):
        # rel_brg = state[1] - state[3]
        rel_brg = state[1]
        state_range = state[0]
        if rel_brg < 0:
            rel_brg += 360
        if (rel_brg <= 60) or (rel_brg >= 300) or (state_range >= self.sensor_range):
            return 1
        if (
            not (self.obs1(state) > 0)
            and not (self.obs2(state) > 0)
            and not (self.obs3(state) > 0)
        ):
            return 1
        if (120 <= rel_brg <= 240) and (
            self.sensor_range / 2 < state_range < self.sensor_range
        ):
            return 2 * state_range / self.sensor_range - 1
        if ((90 <= rel_brg < 120) or (240 < rel_brg <= 270)) and (
            self.sensor_range / 2 < state_range < self.sensor_range
        ):
            return 2 * state_range / self.sensor_range - 1
        if ((60 <= rel_brg < 90) or (270 < rel_brg <= 300)) and (
            self.sensor_range / 2 < state_range < self.sensor_range
        ):
            return 2 * state_range / self.sensor_range - 1
        return 0.0001


AVAIL_SENSORS = {
    "doublerssi": DoubleRSSI,
    "doublerssilofi": DoubleRSSILofi,
    "singlerssi": SingleRSSI,
}


def get_sensor(sensor_name=""):
    """Convenience function for retrieving BirdsEye sensor methods
    Parameters
    ----------
    sensor_name : {'simpleactions'}
        Name of sensor method.
    Returns
    -------
    sensor_obj : Sensor class object
        BirdsEye sensor method.
    """
    if sensor_name in AVAIL_SENSORS:
        sensor_obj = AVAIL_SENSORS[sensor_name]
        return sensor_obj
    raise ValueError(
        "Invalid sensor method name, {}, entered. Must be "
        "in {}".format(sensor_name, AVAIL_SENSORS.keys())
    )
