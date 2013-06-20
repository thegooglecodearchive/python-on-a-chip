#! /usr/bin/env python

# This file is Copyright 2010 Dean Hall.
#
# This file is part of the Python-on-a-Chip program.
# Python-on-a-Chip is free software: you can redistribute it and/or modify
# it under the terms of the GNU LESSER GENERAL PUBLIC LICENSE Version 2.1.
#
# Python-on-a-Chip is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# A copy of the GNU LESSER GENERAL PUBLIC LICENSE Version 2.1
# is seen in the file COPYING up one directory from this.


# Processes a Python code object to ensure it will execute
# in the PyMite virtual machine.


import dis, os, sys


# Maximum number of locals a native func can have (frame.h)
NATIVE_MAX_NUM_LOCALS = 8

# Remove documentation string from const pool
REMOVE_DOC_STR = True

# Masks for co_flags (from CPython's code.h)
CO_OPTIMIZED = 0x0001
CO_NEWLOCALS = 0x0002
CO_VARARGS = 0x0004
CO_VARKEYWORDS = 0x0008
CO_NESTED = 0x0010
CO_GENERATOR = 0x0020
CO_NOFREE = 0x0040

# String used to ID a native method
NATIVE_INDICATOR = "__NATIVE__"
NATIVE_INDICATOR_LENGTH = len(NATIVE_INDICATOR)

MODULE_IDENTIFIER = "<module>"

# Unimplemented bytecodes (from Python 2.6)
UNIMPLEMENTED_BCODES = [
    "STORE_SLICE+0", "STORE_SLICE+1", "STORE_SLICE+2", "STORE_SLICE+3",
    "DELETE_SLICE+0", "DELETE_SLICE+1", "DELETE_SLICE+2", "DELETE_SLICE+3",
    "PRINT_ITEM_TO", "PRINT_NEWLINE_TO",
    "WITH_CLEANUP",
    "EXEC_STMT",
    "END_FINALLY",
    "SETUP_EXCEPT", "SETUP_FINALLY",
    "BUILD_SLICE",
    "CALL_FUNCTION_VAR", "CALL_FUNCTION_KW", "CALL_FUNCTION_VAR_KW",
    "EXTENDED_ARG",
]


def co_filter_factory():
    """Returns a filter function that raises an exception
    if any of the following filters fail:

    Code object fields:
        Ensure consts tuple has fewer than 65536 items.
        Replace constant __doc__ with None if present.

    Flags filter:
        Check co_flags for flags that indicate an unsupported feature
        Supported flags: CO_NOFREE, CO_OPTIMIZED, CO_NEWLOCALS, CO_NESTED, 
            CO_GENERATOR
        Unsupported flags: CO_VARARGS, CO_VARKEYWORDS

    Native code filter:
        If this function has a native indicator,
        extract the native code from the doc string
        and clear the doc string.
        Ensure num args is less or equal to
        NATIVE_MAX_NUM_LOCALS.

    Names/varnames filter:
        Ensure num names is less than 65536.
        If co_name is the module identifier replace it with
        the trimmed module name
        otherwise just append the name to co_name.

    Bcode filter:
        Raise NotImplementedError for an invalid bcode.

    If all is well, return the filtered consts list,
    names list, code string and native code.
    """

    # Set invalid and unimplemented bcodes to None
    clear_invalid = lambda x: None if x[0] == '<' or x in UNIMPLEMENTED_BCODES \
                              else x
    bcodes = map(clear_invalid, dis.opname[:])


    def _filter(co):
        """Returns a dict with entries that mimic the attributes of a code obj.
        Only the fields needed by pmCoCreator.py are duplicated.
        COs are immutable.  Because some CO fields need to be changed, a dict
        is created to hold the changes and the other useful fields.
        """
        
        ## General filter
        # Check sizes of co fields
        assert len(co.co_consts) < 65536, "too many constants."
        assert len(co.co_names) < 65536, "too many names."
        assert co.co_argcount < 256, "too many arguments."
        assert co.co_stacksize < 256, "too large of a stack."
        assert co.co_nlocals < 256, "too many local variables."

        # Check co_flags
        assert co.co_flags & CO_VARARGS == 0, "varargs not supported."
        assert co.co_flags & CO_VARKEYWORDS == 0, "keyword args not supported."

        ## Bcode filter
        # Iterate through the bytecodes
        i = 0
        s = co.co_code
        len_s = len(s)
        while i < len_s:

            # Ensure no illegal bytecodes are present
            c = ord(s[i])
            assert bcodes[c] != None, \
                   "Illegal bytecode (%d/%s/%s) comes at offset %d in file %s."\
                   % (c, hex(c), dis.opname[c], i, co.co_filename)

            # Go to next bytecode (skip 2 extra bytes if there is an argument)
            i += 1
            if c >= dis.HAVE_ARGUMENT:
                i += 2

        # Get trimmed src file name and module name
        fn = os.path.basename(co.co_filename)
        mn = os.path.splitext(fn)[0]


        ## Consts filter
        consts = list(co.co_consts)
        names = list(co.co_names)
        if consts and type(consts[0]) == str:

            ## Native code filter
            # If this CO is intended to be a native func.
            if (consts[0][:NATIVE_INDICATOR_LENGTH] ==
                NATIVE_INDICATOR):

                assert co.co_nlocals <= NATIVE_MAX_NUM_LOCALS, \
                       "Too many args to the native function"

                # Clear Native code from doc string
                consts[0] = None
                if names and names[0] == "__doc__":
                    names[0] = ''

        ## Names filter

        # Remove __doc__ name and docstring if requested
        # WARNING: this heuristic is not always accurate
        if REMOVE_DOC_STR and names and names[0] == "__doc__":
            consts[0] = None
            names[0] = ''

        # If co_name is the module identifier change it to module name
        name = co.co_name
        if name == MODULE_IDENTIFIER:
            name = mn

        # Cellvars is changed into a tuple of indices into co_varnames
        cellvars = [-1,] * len(co.co_cellvars)
        for i,name in enumerate(co.co_cellvars):
            if name in co.co_varnames:
                cellvars[i] = co.co_varnames.index(name)

        d = {}
        d['co_name'] = name
        d['co_filename'] = fn
        d['co_names'] = tuple(names)
        d['co_consts'] = tuple(consts)
        d['co_cellvars'] = tuple(cellvars)
        return d

    return _filter