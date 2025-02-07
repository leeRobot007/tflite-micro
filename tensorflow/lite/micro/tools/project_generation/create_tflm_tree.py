# Copyright 2021 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Starting point for writing scripts to integrate TFLM with external IDEs.

This script can be used to output a tree containing only the sources and headers
needed to use TFLM for a specific configuration (e.g. target and
optimized_kernel_implementation). This should serve as a starting
point to integrate TFLM with external IDEs.

The goal is for this script to be an interface that is maintained by the TFLM
team and any additional scripting needed for integration with a particular IDE
should be written external to the TFLM repository and built to work on top of
the output tree generated with this script.

We will add more documentation for a desired end-to-end integration workflow as
we get further along in our prototyping. See this github issue for more details:
  https://github.com/tensorflow/tensorflow/issues/47413
"""

import argparse
import fileinput
import os
import shutil
import subprocess


def _get_dirs(file_list):
  dirs = set()
  for filepath in file_list:
    dirs.add(os.path.dirname(filepath))
  return dirs


def _get_file_list(key, makefile_options):
  params_list = [
      "make", "-f", "tensorflow/lite/micro/tools/make/Makefile", key
  ] + makefile_options.split()
  process = subprocess.Popen(params_list,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
  stdout, stderr = process.communicate()

  if process.returncode != 0:
    raise RuntimeError("%s failed with \n\n %s" %
                       (" ".join(params_list), stderr.decode()))

  return [bytepath.decode() for bytepath in stdout.split()]


def _third_party_src_and_dest_files(prefix_dir, makefile_options):
  src_files = []
  src_files.extend(_get_file_list("list_third_party_sources",
                                  makefile_options))
  src_files.extend(_get_file_list("list_third_party_headers",
                                  makefile_options))

  # The list_third_party_* rules give path relative to the root of the git repo.
  # However, in the output tree, we would like for the third_party code to be a tree
  # under prefix_dir/third_party, with the path to the tflm_download directory
  # removed. The path manipulation logic that follows removes the downloads
  # directory prefix, and adds the third_party prefix to create a list of
  # destination directories for each of the third party files.
  tflm_download_path = "tensorflow/lite/micro/tools/make/downloads"
  dest_files = [
      os.path.join(prefix_dir, "third_party",
                   os.path.relpath(f, tflm_download_path)) for f in src_files
  ]

  return src_files, dest_files


def _tflm_src_and_dest_files(prefix_dir, makefile_options):
  src_files = []
  src_files.extend(_get_file_list("list_library_sources", makefile_options))
  src_files.extend(_get_file_list("list_library_headers", makefile_options))
  dest_files = [os.path.join(prefix_dir, src) for src in src_files]
  return src_files, dest_files


def _get_src_and_dest_files(prefix_dir, makefile_options):
  tflm_src_files, tflm_dest_files = _tflm_src_and_dest_files(
      prefix_dir, makefile_options)
  third_party_srcs, third_party_dests = _third_party_src_and_dest_files(
      prefix_dir, makefile_options)

  all_src_files = tflm_src_files + third_party_srcs
  all_dest_files = tflm_dest_files + third_party_dests
  return all_src_files, all_dest_files


def _copy(src_files, dest_files):
  for dirname in _get_dirs(dest_files):
    os.makedirs(dirname, exist_ok=True)

  for src, dst in zip(src_files, dest_files):
    shutil.copy(src, dst)


# For examples, we are explicitly making a deicision to not have any source
# specialization based on the TARGET and OPTIMIZED_KERNEL_DIR. The thinking
# here is that any target-specific sources should not be part of the TFLM
# tree. Rather, this function will return an examples directory structure for
# x86 and it will be the responsibility of the target-specific examples
# repository to provide all the additional sources (and remove the unnecessary
# sources) for the examples to run on that specific target.
def _create_examples_tree(prefix_dir, examples_list):
  files = []
  for e in examples_list:
    files.extend(_get_file_list("list_%s_example_sources" % (e), ""))
    files.extend(_get_file_list("list_%s_example_headers" % (e), ""))

  # The get_file_list gives path relative to the root of the git repo (where the
  # examples are in tensorflow/lite/micro/examples). However, in the output
  # tree, we would like for the examples to be under prefix_dir/examples.
  tflm_examples_path = "tensorflow/lite/micro/examples"

  dest_file_list = [
      os.path.join(prefix_dir, "examples",
                   os.path.relpath(f, tflm_examples_path)) for f in files
  ]

  for dest_file, filepath in zip(dest_file_list, files):
    dest_dir = os.path.dirname(dest_file)
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy(filepath, dest_dir)

  # Since we are changing the directory structure for the examples, we will also
  # need to modify the paths in the code.
  for filepath in dest_file_list:
    # We need a trailing forward slash because what we care about is replacing
    # the include paths.
    text_to_replace = os.path.join(
        tflm_examples_path, os.path.basename(os.path.dirname(filepath))) + "/"

    with fileinput.FileInput(filepath, inplace=True) as f:
      for line in f:
        # end="" prevents an extra newline from getting added as part of the
        # in-place find and replace.
        print(line.replace(text_to_replace, ""), end="")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Starting script for TFLM project generation")
  parser.add_argument("output_dir",
                      help="Output directory for generated TFLM tree")
  parser.add_argument("--no_copy",
                      action="store_true",
                      help="Do not copy files to output directory")
  parser.add_argument(
      "--no_download",
      action="store_true",
      help="Do not download the TFLM third_party dependencies.")
  parser.add_argument("--print_src_files",
                      action="store_true",
                      help="Print the src files (i.e. files in the TFLM tree)")
  parser.add_argument(
      "--print_dest_files",
      action="store_true",
      help="Print the dest files (i.e. files in the output tree)")
  parser.add_argument("--makefile_options",
                      default="",
                      help="Additional TFLM Makefile options. For example: "
                      "--makefile_options=\"TARGET=<target> "
                      "OPTIMIZED_KERNEL_DIR=<optimized_kernel_dir> "
                      "TARGET_ARCH=corex-m4\"")
  parser.add_argument("--examples",
                      "-e",
                      action="append",
                      help="Examples to add to the output tree. For example: "
                      "-e hello_world -e micro_speech")
  args = parser.parse_args()

  makefile_options = args.makefile_options
  if args.no_download:
    makefile_options += " DISABLE_DOWNLOADS=true"
  else:
    # TODO(b/143904317): Explicitly call make third_party_downloads. This will
    # no longer be needed once all the downloads are switched over to bash
    # scripts.
    params_list = [
        "make", "-f", "tensorflow/lite/micro/tools/make/Makefile",
        "third_party_downloads"
    ] + makefile_options.split()
    process = subprocess.Popen(params_list,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
      raise RuntimeError("%s failed with \n\n %s" %
                         (" ".join(params_list), stderr.decode()))

  src_files, dest_files = _get_src_and_dest_files(args.output_dir,
                                                  makefile_options)

  if args.print_src_files:
    print(" ".join(src_files))

  if args.print_dest_files:
    print(" ".join(dest_files))

  if args.no_copy is False:
    _copy(src_files, dest_files)

  if args.examples is not None:
    _create_examples_tree(args.output_dir, args.examples)
