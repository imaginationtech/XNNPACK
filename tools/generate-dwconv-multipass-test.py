#!/usr/bin/env python
# Copyright 2019 Google LLC
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import bisect
import codecs
import math
import os
import re
import sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from primes import next_prime
import xngen
import xnncommon


parser = argparse.ArgumentParser(description='XNNPACK generator')
parser.add_argument("-s", "--spec", metavar="FILE", required=True,
                    help="Spec (YAML) file")
parser.add_argument("-o", "--output", metavar="FILE", required=True,
                    help='Output (C++ source) file')
parser.set_defaults(defines=list())

def split_ukernel_name(name):
  common_name, target_name = name.split("__", 1)
  common_parts = common_name.split("_")
  param_spec = common_parts[-1]

  m = re.search(r'(\d+)f(\d+)m(\d+)l(\d+)c', param_spec)
  assert m
  first_pass_tile = int(m[1])
  middle_pass_tile = int(m[2])
  last_pass_tile = int(m[3])
  cr = int(m[4])
  arch, isa = xnncommon.parse_target_name(target_name)

  requantization = common_parts[-3]
  if requantization not in ["fp32", "rndnu"]:
    requantization = None

  return first_pass_tile, middle_pass_tile, last_pass_tile, cr, requantization, arch, isa


DWCONV_TEST_CODE = """\
TEST(${TEST_NAME}, c_eq_${CBLOCK}_first_pass_plus_one) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  DWConvMicrokernelTester()
    .first_pass_tile(${FIRST_PASS_TILE})
    .middle_pass_tile(${MIDDLE_PASS_TILE})
    .last_pass_tile(${LAST_PASS_TILE})
    .cr(${CR})
    .channel_subtile(${CHANNEL_SUBTILE})
    .kr(${FIRST_PASS_TILE+1})
    .channels(${CBLOCK})
    .Test(${", ".join(TEST_ARGS)});
}

TEST(${TEST_NAME}, c_eq_${CBLOCK}_first_pass_and_last_pass) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  DWConvMicrokernelTester()
    .first_pass_tile(${FIRST_PASS_TILE})
    .middle_pass_tile(${MIDDLE_PASS_TILE})
    .last_pass_tile(${LAST_PASS_TILE})
    .cr(${CR})
    .channel_subtile(${CHANNEL_SUBTILE})
    .kr(${FIRST_PASS_TILE+LAST_PASS_TILE})
    .channels(${CBLOCK})
    .Test(${", ".join(TEST_ARGS)});
}

TEST(${TEST_NAME}, c_eq_${CBLOCK}_multipass) {
  for (uint32_t kr = ${FIRST_PASS_TILE+MIDDLE_PASS_TILE+LAST_PASS_TILE}; kr < ${FIRST_PASS_TILE+MIDDLE_PASS_TILE*2+LAST_PASS_TILE}; kr++) {
    $if ISA_CHECK:
      ${ISA_CHECK};
    DWConvMicrokernelTester()
      .first_pass_tile(${FIRST_PASS_TILE})
      .middle_pass_tile(${MIDDLE_PASS_TILE})
      .last_pass_tile(${LAST_PASS_TILE})
      .cr(${CR})
      .channel_subtile(${CHANNEL_SUBTILE})
      .kr(kr)
      .channels(${CBLOCK})
      .Test(${", ".join(TEST_ARGS)});
  }
}

$if CBLOCK > 1:
  TEST(${TEST_NAME}, c_div_${CBLOCK}_first_pass_plus_one) {
    $if ISA_CHECK:
      ${ISA_CHECK};
    for (uint32_t channels = ${ADJCBLOCK + CBLOCK}; channels < ${CR * 16}; channels += ${CR * 3}) {
      DWConvMicrokernelTester()
        .first_pass_tile(${FIRST_PASS_TILE})
        .middle_pass_tile(${MIDDLE_PASS_TILE})
        .last_pass_tile(${LAST_PASS_TILE})
        .cr(${CR})
        .channel_subtile(${CHANNEL_SUBTILE})
        .kr(${FIRST_PASS_TILE+1})
        .channels(channels)
        .Test(${", ".join(TEST_ARGS)});
    }
  }

  TEST(${TEST_NAME}, c_div_${CBLOCK}_first_pass_and_last_pass) {
    $if ISA_CHECK:
      ${ISA_CHECK};
    for (uint32_t channels = ${ADJCBLOCK + CBLOCK}; channels < ${CR * 16}; channels += ${CR * 3}) {
      DWConvMicrokernelTester()
        .first_pass_tile(${FIRST_PASS_TILE})
        .middle_pass_tile(${MIDDLE_PASS_TILE})
        .last_pass_tile(${LAST_PASS_TILE})
        .cr(${CR})
        .channel_subtile(${CHANNEL_SUBTILE})
        .kr(${FIRST_PASS_TILE+LAST_PASS_TILE})
        .channels(channels)
        .Test(${", ".join(TEST_ARGS)});
    }
  }

  TEST(${TEST_NAME}, c_div_${CBLOCK}_multipass) {
    $if ISA_CHECK:
      ${ISA_CHECK};
    for (uint32_t channels = ${ADJCBLOCK + CBLOCK}; channels < ${CR * 16}; channels += ${CR * 3}) {
      for (uint32_t kr = ${FIRST_PASS_TILE+MIDDLE_PASS_TILE+LAST_PASS_TILE}; kr < ${FIRST_PASS_TILE+MIDDLE_PASS_TILE*2+LAST_PASS_TILE}; kr++) {
        DWConvMicrokernelTester()
          .first_pass_tile(${FIRST_PASS_TILE})
          .middle_pass_tile(${MIDDLE_PASS_TILE})
          .last_pass_tile(${LAST_PASS_TILE})
          .cr(${CR})
          .channel_subtile(${CHANNEL_SUBTILE})
          .kr(kr)
          .channels(channels)
          .Test(${", ".join(TEST_ARGS)});
      }
    }
  }

  $if ACTIVATION == "MINMAX":
    TEST(${TEST_NAME}, c_div_${CBLOCK}_with_qmin) {
      $if ISA_CHECK:
        ${ISA_CHECK};
      for (uint32_t channels = ${ADJCBLOCK + CBLOCK}; channels < ${CR * 16}; channels += ${CR * 3}) {
        DWConvMicrokernelTester()
          .first_pass_tile(${FIRST_PASS_TILE})
          .middle_pass_tile(${MIDDLE_PASS_TILE})
          .last_pass_tile(${LAST_PASS_TILE})
          .cr(${CR})
          .channel_subtile(${CHANNEL_SUBTILE})
          .kr(${FIRST_PASS_TILE+LAST_PASS_TILE})
          .channels(channels)
          .qmin(128)
          .Test(${", ".join(TEST_ARGS)});
      }
    }

    TEST(${TEST_NAME}, c_div_${CBLOCK}_with_qmax) {
      $if ISA_CHECK:
        ${ISA_CHECK};
      for (uint32_t channels = ${ADJCBLOCK + CBLOCK}; channels < ${CR * 16}; channels += ${CR * 3}) {
        DWConvMicrokernelTester()
          .first_pass_tile(${FIRST_PASS_TILE})
          .middle_pass_tile(${MIDDLE_PASS_TILE})
          .last_pass_tile(${LAST_PASS_TILE})
          .cr(${CR})
          .channel_subtile(${CHANNEL_SUBTILE})
          .kr(${FIRST_PASS_TILE+LAST_PASS_TILE})
          .channels(channels)
          .qmax(128)
          .Test(${", ".join(TEST_ARGS)});
      }
    }

TEST(${TEST_NAME}, c_gt_${ADJCBLOCK}_first_pass_plus_one) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (uint32_t channels = ${ADJCBLOCK + 1}; channels < ${10 if CBLOCK == 1 else ADJCBLOCK + CBLOCK}; channels++) {
    DWConvMicrokernelTester()
      .first_pass_tile(${FIRST_PASS_TILE})
      .middle_pass_tile(${MIDDLE_PASS_TILE})
      .last_pass_tile(${LAST_PASS_TILE})
      .cr(${CR})
      .channel_subtile(${CHANNEL_SUBTILE})
      .kr(${FIRST_PASS_TILE+1})
      .channels(channels)
      .Test(${", ".join(TEST_ARGS)});
  }
}

TEST(${TEST_NAME}, c_gt_${ADJCBLOCK}_first_pass_and_last_pass) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (uint32_t channels = ${ADJCBLOCK + 1}; channels < ${10 if CBLOCK == 1 else ADJCBLOCK + CBLOCK}; channels++) {
    DWConvMicrokernelTester()
      .first_pass_tile(${FIRST_PASS_TILE})
      .middle_pass_tile(${MIDDLE_PASS_TILE})
      .last_pass_tile(${LAST_PASS_TILE})
      .cr(${CR})
      .channel_subtile(${CHANNEL_SUBTILE})
      .kr(${FIRST_PASS_TILE+LAST_PASS_TILE})
      .channels(channels)
      .Test(${", ".join(TEST_ARGS)});
  }
}

TEST(${TEST_NAME}, c_gt_${ADJCBLOCK}_multipass) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (uint32_t channels = ${ADJCBLOCK + 1}; channels < ${10 if CBLOCK == 1 else ADJCBLOCK + CBLOCK}; channels++) {
    for (uint32_t kr = ${FIRST_PASS_TILE+MIDDLE_PASS_TILE+LAST_PASS_TILE}; kr < ${FIRST_PASS_TILE+MIDDLE_PASS_TILE*2+LAST_PASS_TILE}; kr++) {
      DWConvMicrokernelTester()
        .first_pass_tile(${FIRST_PASS_TILE})
        .middle_pass_tile(${MIDDLE_PASS_TILE})
        .last_pass_tile(${LAST_PASS_TILE})
        .cr(${CR})
        .channel_subtile(${CHANNEL_SUBTILE})
        .kr(kr)
        .channels(channels)
        .Test(${", ".join(TEST_ARGS)});
    }
  }
}

TEST(${TEST_NAME}, c_eq_${CBLOCK}_first_pass_plus_one_multipixel) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (size_t channels = 1; channels <= ${CBLOCK * 5}; channels += ${max(1, CBLOCK - 1)}) {
    DWConvMicrokernelTester()
      .first_pass_tile(${FIRST_PASS_TILE})
      .middle_pass_tile(${MIDDLE_PASS_TILE})
      .last_pass_tile(${LAST_PASS_TILE})
      .cr(${CR})
      .channel_subtile(${CHANNEL_SUBTILE})
      .kr(${FIRST_PASS_TILE+1})
      .channels(channels)
      .width(3)
      .Test(${", ".join(TEST_ARGS)});
  }
}

TEST(${TEST_NAME}, c_eq_${CBLOCK}_first_pass_and_last_pass_multipixel) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (size_t channels = 1; channels <= ${CBLOCK * 5}; channels += ${max(1, CBLOCK - 1)}) {
    DWConvMicrokernelTester()
      .first_pass_tile(${FIRST_PASS_TILE})
      .middle_pass_tile(${MIDDLE_PASS_TILE})
      .last_pass_tile(${LAST_PASS_TILE})
      .cr(${CR})
      .channel_subtile(${CHANNEL_SUBTILE})
      .kr(${FIRST_PASS_TILE+LAST_PASS_TILE})
      .channels(channels)
      .width(3)
      .Test(${", ".join(TEST_ARGS)});
  }
}

TEST(${TEST_NAME}, c_eq_${CBLOCK}_multipass_multipixel) {
  for (size_t channels = 1; channels <= ${CBLOCK * 5}; channels += ${max(1, CBLOCK - 1)}) {
    for (uint32_t kr = ${FIRST_PASS_TILE+MIDDLE_PASS_TILE+LAST_PASS_TILE}; kr < ${FIRST_PASS_TILE+MIDDLE_PASS_TILE*2+LAST_PASS_TILE}; kr++) {
      $if ISA_CHECK:
        ${ISA_CHECK};
      DWConvMicrokernelTester()
        .first_pass_tile(${FIRST_PASS_TILE})
        .middle_pass_tile(${MIDDLE_PASS_TILE})
        .last_pass_tile(${LAST_PASS_TILE})
        .cr(${CR})
        .channel_subtile(${CHANNEL_SUBTILE})
        .kr(kr)
        .channels(channels)
        .width(3)
        .Test(${", ".join(TEST_ARGS)});
    }
  }
}

TEST(${TEST_NAME}, multipixel_with_step) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (size_t channels = 1; channels <= ${CBLOCK * 5}; channels += ${max(1, CBLOCK - 1)}) {
    for (uint32_t kr = ${FIRST_PASS_TILE+MIDDLE_PASS_TILE+LAST_PASS_TILE}; kr < ${FIRST_PASS_TILE+MIDDLE_PASS_TILE*2+LAST_PASS_TILE}; kr++) {
      for (size_t step = 2; step <= ${KR}; step++) {
        DWConvMicrokernelTester()
          .first_pass_tile(${FIRST_PASS_TILE})
          .middle_pass_tile(${MIDDLE_PASS_TILE})
          .last_pass_tile(${LAST_PASS_TILE})
          .cr(${CR})
          .channel_subtile(${CHANNEL_SUBTILE})
          .kr(kr)
          .channels(channels)
          .width(3)
          .step(step)
          .Test(${", ".join(TEST_ARGS)});
      }
    }
  }
}

TEST(${TEST_NAME}, multipixel_with_output_stride) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (size_t channels = 1; channels <= ${CBLOCK * 5}; channels += ${max(1, CBLOCK - 1)}) {
    for (uint32_t kr = ${FIRST_PASS_TILE+MIDDLE_PASS_TILE+LAST_PASS_TILE}; kr < ${FIRST_PASS_TILE+MIDDLE_PASS_TILE*2+LAST_PASS_TILE}; kr++) {
      DWConvMicrokernelTester()
        .first_pass_tile(${FIRST_PASS_TILE})
        .middle_pass_tile(${MIDDLE_PASS_TILE})
        .last_pass_tile(${LAST_PASS_TILE})
        .cr(${CR})
        .channel_subtile(${CHANNEL_SUBTILE})
        .kr(kr)
        .channels(channels)
        .width(5)
        .output_stride(${next_prime(CR * 5 + 1)})
        .Test(${", ".join(TEST_ARGS)});
    }
  }
}

TEST(${TEST_NAME}, input_offset) {
  $if ISA_CHECK:
    ${ISA_CHECK};
  for (uint32_t channels = ${ADJCBLOCK + CBLOCK}; channels < ${CR * 16}; channels += ${CR * 3}) {
    for (uint32_t kr = ${FIRST_PASS_TILE+MIDDLE_PASS_TILE+LAST_PASS_TILE}; kr < ${FIRST_PASS_TILE+MIDDLE_PASS_TILE*2+LAST_PASS_TILE}; kr++) {
      DWConvMicrokernelTester()
        .first_pass_tile(${FIRST_PASS_TILE})
        .middle_pass_tile(${MIDDLE_PASS_TILE})
        .last_pass_tile(${LAST_PASS_TILE})
        .cr(${CR})
        .channel_subtile(${CHANNEL_SUBTILE})
        .kr(kr)
        .channels(channels)
        .input_offset(${next_prime(CR + 1) * 16})
        .Test(${", ".join(TEST_ARGS)});
    }
  }
}
"""


def channel_subtile_from_isa(isa):
  if isa == 'sse':
    return 4
  assert False


def generate_test_cases(ukernel, first_pass_tile, middle_pass_tile, last_pass_tile, cr, c_block,
                        init_fn, requantization, is_pipelined, isa):
  """Generates all tests cases for a DWCONV micro-kernel.

  Args:
    ukernel: C name of the micro-kernel function.
    cr: CR parameter of the DWCONV micro-kernel.
    kr: KR parameter of the DWCONV micro-kernel.
    k_block: Number of C values processed per one iteration of the main loop of
             the micro-kernel.
    init_fn: C name of the function to initialize microkernel parameters.
    requantization: name of the requantization scheme used by the microkernel.
    is_pipelined: Indicates if the micro-kernel is implemented with software
                  pipelining. Additional test cases are generated for software
                  pipelined micro-kernels to separately test prologue + epiloque
                  of the pipelined loop and iteration of the pipelined loop.
    isa: instruction set required to run the micro-kernel. Generated unit test
         will skip execution if the host processor doesn't support this ISA.

  Returns:
    Code for the test case.
  """
  kr = first_pass_tile
  _, test_name = ukernel.split("_", 1)
  _, datatype, ukernel_type, activation, _ = ukernel.split("_", 4)
  if activation == "ukernel":
    activation = "linear"
  test_args = [ukernel]
  if init_fn:
    test_args.append(init_fn)
    if requantization:
      requantization_datatype = {"qc8": "qs8"}.get(datatype, datatype)
      test_args.append("xnn_%s_requantize_%s" %
        (requantization_datatype, requantization))
  return xngen.preprocess(DWCONV_TEST_CODE, {
      "TEST_NAME": test_name.upper().replace("UKERNEL_", ""),
      "TEST_ARGS": test_args,
      "UKERNEL_TYPE": ukernel_type.upper(),
      "DATATYPE": datatype,
      "ACTIVATION": activation.upper(),
      "FIRST_PASS_TILE": first_pass_tile,
      "MIDDLE_PASS_TILE": middle_pass_tile,
      "LAST_PASS_TILE": last_pass_tile,
      "CR": cr,
      "CHANNEL_SUBTILE": channel_subtile_from_isa(isa),
      "KR": kr,
      "CBLOCK": c_block,
      "ADJCBLOCK": 2 * c_block if is_pipelined else c_block,
      "IS_PIPELINED": is_pipelined,
      "ISA_CHECK": xnncommon.generate_isa_check_macro(isa),
      "next_prime": next_prime,
      "sqrt": math.sqrt,
    })


def main(args):
  options = parser.parse_args(args)

  with codecs.open(options.spec, "r", encoding="utf-8") as spec_file:
    spec_yaml = yaml.safe_load(spec_file)
    if not isinstance(spec_yaml, list):
      raise ValueError("expected a list of micro-kernels in the spec")

    tests = """\
// Copyright 2022 Google LLC
//
// This source code is licensed under the BSD-style license found in the
// LICENSE file in the root directory of this source tree.
//
// Auto-generated file. Do not edit!
//   Specification: {specification}
//   Generator: {generator}


#include <gtest/gtest.h>

#include <xnnpack/common.h>
#include <xnnpack/isa-checks.h>

#include <xnnpack/dwconv.h>
#include "dwconv-microkernel-tester.h"
""".format(specification=options.spec, generator=sys.argv[0])

    for ukernel_spec in spec_yaml:
      name = ukernel_spec["name"]
      init_fn = ukernel_spec.get("init")
      pipelined = bool(ukernel_spec.get("pipelined", False))
      assembly = bool(ukernel_spec.get("assembly", False))
      first_pass_tile, middle_pass_tile, last_pass_tile, cr, requantization, arch, isa = split_ukernel_name(name)

      # specification can override architecture
      arch = ukernel_spec.get("arch", arch)

      test_case = generate_test_cases(
        name, first_pass_tile, middle_pass_tile, last_pass_tile, cr, cr, init_fn, requantization, pipelined, isa)
      tests += "\n\n" + xnncommon.postprocess_test_case(test_case, arch, isa, assembly)

    txt_changed = True
    if os.path.exists(options.output):
      with codecs.open(options.output, "r", encoding="utf-8") as output_file:
        txt_changed = output_file.read() != tests

    if txt_changed:
      with codecs.open(options.output, "w", encoding="utf-8") as output_file:
        output_file.write(tests)


if __name__ == "__main__":
  main(sys.argv[1:])
