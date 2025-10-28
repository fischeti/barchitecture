#!/usr/bin/env python
# Copyright 2023 ETH Zurich and University of Bologna.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
#
# Author: Tim Fischer <fischeti@iis.ee.ethz.ch>

from pathlib import Path
import matplotlib.path as mpath
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

import argparse
import json
import jsonref
from jsonschema import Draft202012Validator, validators

from colors import PULPColors

# Extend jsonschema to set defaults
def extend_with_default(validator_class):
    validate_props = validator_class.VALIDATORS["properties"]
    def set_defaults(validator, properties, instance, schema):
        if not isinstance(instance, dict):
            return
        # insert defaults for missing properties
        for prop, subschema in properties.items():
            if "default" in subschema and prop not in instance:
                instance[prop] = json.loads(json.dumps(subschema["default"]))  # copy
        # continue normal validation (recurse)
        for error in validate_props(validator, properties, instance, schema):
            yield error
    return validators.extend(validator_class, {"properties": set_defaults})


def preprocess_data(data):
    """Preprocess data to compute totals and normalized values."""
    for bar in data["bars"].values():
        bar["total"] = sum(bar["values"])
        bar["norm_values"] = [x / bar["total"] for x in bar["values"]]
        bar["left"] = [
            sum(bar["norm_values"][:j]) for j, v in enumerate(bar["norm_values"])
        ]
        bar["right"] = [sum(x) for x in zip(bar["left"], bar["norm_values"])]
        if not bar["label_offset"]:
            bar["label_offset"] = [0] * len(bar["labels"])
        if not bar["label_offset_y"]:
            bar["label_offset_y"] = [0] * len(bar["labels"])
        if not bar["value_offset"]:
            bar["value_offset"] = [0] * len(bar["labels"])

    return data


def curve_between_points(p1, p2, curve_height=0.5):
    curve_height = -curve_height if p2[1] < p1[1] else curve_height
    path_area = [
        (mpath.Path.CURVE4, (p1[0], p1[1] + curve_height)),
        (mpath.Path.CURVE4, (p2[0], p2[1] - curve_height)),
        (mpath.Path.CURVE4, p2),
    ]
    return path_area


def plot(data, show_plot=False, output_path=None):
    """Generate hierarchical breakdown bar plot."""

    si_unit = data["si_unit"]
    bars = data["bars"]
    fmt = data["fmt"]
    bar_height = data["fig"]["bar_height"]

    if data["fig"]["fontfamily"]:
        plt.rcParams["font.family"] = data["fig"]["fontfamily"]

    fontdict = {
        "fontsize": data["fig"]["fontsize"],
        "fontfamily": data["fig"]["fontfamily"],
    }
    smallfontdict = {
        "fontsize": data["fig"]["fontsize"] * 0.8,
        "fontfamily": data["fig"]["fontfamily"],
    }

    fig_height = (bar_height * len(bars) + 0.5) * data["fig"]["scale"]
    fig_width = fig_height * data["fig"]["ratio"]
    _, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.invert_yaxis()
    ax.xaxis.set_visible(False)
    ax.set_xlim(0, 1)

    for i, bar in enumerate(bars.values()):
        for j in range(len(bar["labels"])):
            label = bar["labels"][j]
            value = bar["values"][j]
            norm_value = bar["norm_values"][j]
            color = bar["colors"][j]
            left = bar["left"][j]
            label_offset = bar["label_offset"][j]
            label_offset_y = bar["label_offset_y"][j]
            value_offset = bar["value_offset"][j]
            # Plot bars
            ax.barh(i, norm_value, color=color, left=left, height=bar_height)
            # Plot total value
            ax.text(
                1.02,
                i,
                fmt.format(bar["total"]),
                ha="left",
                va="center",
                color="black",
                weight="bold",
                **fontdict,
            )
            # Plot labels
            ax.text(
                left + norm_value / 2 + label_offset,
                i - 1.1 * bar_height - label_offset_y,
                label,
                ha="center",
                va="center",
                color="black",
                weight="bold",
                **fontdict,
            )
            # Plot norm_values below bars
            perc_number = value / next(iter(bars.values()))["total"] * 100
            perc_fmt = (
                f"{perc_number:.1f}" if perc_number < 10 else f"{perc_number:.0f}"
            )
            ax.text(
                left + norm_value / 2 + value_offset,
                i + 1.1 * bar_height,
                fmt.format(value),
                ha="center",
                va="center",
                color="black",
                weight="bold",
                **smallfontdict,
            )
            ax.text(
                left + norm_value / 2 + value_offset,
                i + 1.1 * 1.5 * bar_height,
                perc_fmt,
                ha="center",
                va="center",
                color="black",
                **smallfontdict,
            )
            # Plot ticks to labels and values
            ax.plot(
                [left + norm_value / 2, left + norm_value / 2 + label_offset],
                [i - 1.2 * bar_height / 2, i - 1.7 * bar_height / 2 - label_offset_y],
                color="black",
                linewidth=0.5,
            )
            ax.plot(
                [left + norm_value / 2, left + norm_value / 2 + value_offset],
                [i + 1.2 * bar_height / 2, i + 1.4 * bar_height / 2],
                color="black",
                linewidth=0.5,
            )
            # Plot separation lines
            if left != 0:
                ax.plot(
                    [left, left],
                    [i - bar_height / 2, i + bar_height / 2],
                    color="white",
                    linewidth=1.5,
                    linestyle="dotted",
                )

        # Plot shades
        if "parent" in bar:
            parent_bar_name, parent_subbar_name = bar["parent"].split(":")
            parent_bar = bars[parent_bar_name]
            parent_idx = list(bars).index(parent_bar_name)
            v_dir = -1 if i < parent_idx else 1
            block_idx = list(parent_bar["labels"]).index(parent_subbar_name)
            Path = mpath.Path
            path_area = [
                (
                    Path.MOVETO,
                    (
                        parent_bar["left"][block_idx],
                        parent_idx + v_dir * bar_height / 2,
                    ),
                )
            ]
            path_area += [
                (
                    Path.LINETO,
                    (
                        parent_bar["right"][block_idx],
                        parent_idx + v_dir * bar_height / 2,
                    ),
                )
            ]
            path_area += curve_between_points(
                (parent_bar["right"][block_idx], parent_idx + v_dir * bar_height / 2),
                (1, i - v_dir * bar_height / 2),
            )
            path_area += [(Path.LINETO, (0, i - v_dir * bar_height / 2))]
            path_area += curve_between_points(
                (0, i - v_dir * bar_height / 2),
                (parent_bar["left"][block_idx], parent_idx + v_dir * bar_height / 2),
            )
            path_area += [
                (
                    Path.CLOSEPOLY,
                    (parent_bar["left"][block_idx], i - 1 + v_dir * bar_height / 2),
                )
            ]
            codes, verts = zip(*path_area)
            path = mpath.Path(verts, codes)
            patch = mpatches.PathPatch(
                path, color=PULPColors["GrayLight"], fill=True, linewidth=0, alpha=0.4
            )
            ax.add_patch(patch)

        # Plot Units
        ax.text(
            1.04,
            len(bars) - 1 + 0.2,
            si_unit,
            ha="center",
            va="center",
            color="black",
            weight="bold",
            **fontdict,
        )
        ax.text(
            1.04,
            len(bars) - 1 + 0.35,
            "%",
            ha="center",
            va="center",
            color="black",
            **smallfontdict,
        )

    if show_plot:
        plt.show()
    else:
        plt.axis("off")
        plt.savefig(output_path, bbox_inches="tight", pad_inches=0.1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate hierarchical breakdown bar plots."
    )
    parser.add_argument("data", type=Path, help="Path to the JSON data file.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path.cwd() / "breakdown_plot.pdf",
        help="Output file path for the generated plot.",
    )
    parser.add_argument(
        "--show", "-s", action="store_true", help="Show the plot instead of saving it."
    )
    args = parser.parse_args()

    with open(args.data, "r") as f:
        data = jsonref.load(f, proxies=False)

    with open("src/data.schema.json", "r") as f:
        schema = json.load(f)

    DefaultingValidator = extend_with_default(Draft202012Validator)
    DefaultingValidator(schema).validate(data)

    data = preprocess_data(data)

    plot(
        data,
        show_plot=args.show,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
