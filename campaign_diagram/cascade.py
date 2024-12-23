import copy

from typing import Tuple
from typing import List

from deprecated import deprecated

from ruamel.yaml import YAML

import logging


from campaign_diagram.kernel import *
from campaign_diagram.intervals import *

kernel_color_map = KernelColor()

class Cascade:
    """A class to manage a collection of Kernel instances."""

    # TODO: add support for  "+"
    # TODO: add supprot for len()

    def __init__(self, kernels: List[Kernel], name="", sequential=False):

        self.logger = logging.getLogger('campaign_diagram.cascade')
        self.logger.setLevel(logging.INFO)

        self.name = name

        if sequential:
            self.assign_starts(kernels)

        self.intervals = Intervals(kernels)


    @classmethod
    def fromYAML(cls, yaml_file):
        """ Creat a cascade from a YAML file """

        yaml = YAML()  # Initialize ruamel.yaml parser
        with open(yaml_file, 'r') as file:
            data = yaml.load(file)


        cascade_data = data.get('cascade', {})
        name = cascade_data.get('name', 'Unnamed Cascade')

        kernels = []
        for kernel_data in cascade_data.get('kernels', []):
            kernel = Kernel(
                name=kernel_data.get('name'),
                duration=kernel_data.get('duration'),
                compute_util=kernel_data.get('compute_util'),
                bw_util=kernel_data.get('bw_util')
            )
            kernels.append(kernel)

        return cls(name=name,
                   kernels=kernels,
                   sequential=True)

    @classmethod
    def fromIntervals(cls, name, intervals):
        """ Create a csacade from an interval data structure """

        c = cls(name=name, kernels=[])
        c.intervals = intervals

        return c

    @property
    def kernels(self):
        """ Flatten intevals into a flat list of kernels """

        return self.intervals.flatten()

    def __len__(self):

        # TODO: Optimize?

        return len(self.kernels)


    def __iter__(self):
        """Return an iterator over the Kernel instances."""

        return iter(self.kernels)

    def duration(self):
       """ Find duration of cascade """

       return self.intervals.duration()

    def avg_compute_util(self):
        """ Return average compute util """

        return self.intervals.avg_compute_util()

    def avg_bw_util(self):
        """ Return average  bw util """

        return self.intervals.avg_bw_util()

    def is_sequential(self):

        last_end = 0

        for kernel in self.kernels:
            if kernel.start != last_end:
                return False

            last_end = kernel.end

        return True

#    def sort(self):
#        """ Sort the kernels by start time for display """
#
#        self.kernels = sorted(self.kernels,
#                              key=lambda k: (k.start, -k.bw_util, k.compute_util, k.name))

    def assign_starts(self, kernels, offset=0):
        """ Assume the tasks are sequential and assign start times """

        last_end = offset
        for kernel in kernels:
            kernel.set_start(last_end)
            last_end = kernel.end

    def assign_colors(self):

        for kernel in self.kernels:
            name = kernel.name
            kernel.set_color(kernel_color_map.getColor(name))

    @deprecated(reason="Cascade.split() has been replaced by Cascade.tile()")
    def split(self, parts):
        return self.tile(parts)

    def tile(self, parts):
        """Tile by splitting each task of a cascade into "parts" parts

        Note: This only works for a cascade that is a simple
        sequential series of kernels.

        Todo: Check invariant!

        """

        parts_fraction = 1.0/parts

        split_kernels = []

        for kernel in self.kernels:
            split_kernels.append(kernel.copy().scale_duration(parts_fraction))

        split_cascade = Cascade(name=f"{self.name} (Tiled)",
                                kernels=[kernel.clone() for kernel in parts*split_kernels],
                                sequential=True)

        return split_cascade

    def pipeline(self, stages=2, spread=False):
        """Pipeline a set of tasks

        Note: Input must be a sequential set of tiles
        Note: This is not meaningful after a cascade is throttled

        """

        assert self.is_sequential()

        tasks = []

        orig_kernels = copy.deepcopy(self.kernels)

        for stage in range(stages):
            name = orig_kernels[stage].name
            task = self._create_spacers(stage, name)
            task.extend(orig_kernels[stage::stages])
            task.extend(self._create_spacers(stages-stage-1, name))

            tasks.append(task)

        # Start with a default previous_end value of zero
        new_kernels = []
        previous_end = 0

        # Iterate over both lists in tandem
        for kernels in zip(*tasks):

            max_duration = max([kernel.duration for kernel in kernels])

            for kernel in kernels:

                # Just skip kernels with duration == 0
                if kernel.duration == 0:
                    continue

                kernel.set_start(previous_end)

                if spread:
                    if kernel.duration !=0 and kernel.duration < max_duration:
                        kernel.dilate(max_duration/kernel.duration)

                new_kernels.append(kernel)

            # TODO: Handle resource overutilization

            previous_end += max_duration

        t = Cascade(name=f"{self.name} (Pipelined)",
                    kernels=new_kernels)

        return t

    def _create_spacers(self, count, name=None):

        spacer = Kernel(name=name,
                        duration=0,
                        compute_util=0,
                        bw_util=0)

        spacers =  [copy.copy(spacer) for _ in range(count)]

        return spacers

    def throttle(self):
        """Throttle a cascde to keep within resource constraints."""

        self.logger.debug("Starting throttle")

        new_intervals = copy.deepcopy(self.intervals)

        # Throttle the kernels in place
        new_intervals.throttle()

        return Cascade.fromIntervals(name=f"{self.name} (Throttled)",
                                     intervals=new_intervals)


    def pretty_print(self, intervals=False):

        print(f"Cascade: {self.name}")

        if not intervals:
            for kernel in self.kernels:
                print(f"{kernel}")
        else:
            self.intervals.pretty_print()

    def __str__(self):
        """Returns a human-readable string representation of the CampaignDiagram's state."""

        kernel_states = "\n".join([str(kernel) for kernel in self.kernels])
        return f"Cascade: {self.name} with kernels:\n{kernel_states}"
