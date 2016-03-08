'''
Created on Feb 16, 2016

@author: mike
'''
from __future__ import print_function

import os
import codecs
import sys
from patgen.margins import Margins
from patgen import stagger_range, EMPTYSET
from patgen.dictionary import Dictionary, format_dictionary_word
from patgen.project import Project
from patgen.selector import Selector
from patgen.range import Range
from patgen.layer import Layer


def main_new(args):
    
    if os.path.exists(args.project):
        print('Project file already exists! Use different name or delete old project first. File %s' % args.project)
        return -1
    
    if not os.path.exists(args.dictionary):
        print('Dictionary file not found', args.dictionary)
        return -1
    
    dictionary = Dictionary.load(args.dictionary)
    for word in dictionary.keys():
        dictionary.missed[word].clear()
        dictionary.missed[word].update(dictionary[word])  # all hyphens are initially missing
        dictionary.false[word].clear()

    if args.margins is None:
        print('Automatically computing hyphenation margins from dictionary')
        margins = dictionary.compute_margins()
    else:
        margins = Margins.parse(args.margins)

    project = Project(dictionary, margins, dictionary.compute_total_hyphens())
    project.save(args.project)

    print('Created project', args.project, 'from dictionary', args.dictionary)
    print()

    return main_show(args)


def main_show(args):
    
    if not os.path.exists(args.project):
        print('Project file not found:', args.project)
        return -1
    
    project = Project.load(args.project)
    
    print('Project file', args.project)
    print('\tcreated:', project.created)
    print('\tlast modified:', project.modified)
    print('\tmargins:', project.margins)
    print('\tdictionary size:', len(project.dictionary.keys()))
    #if project.ignore_weights:
    #    print('\tdictionary weights were ignored (-i flag active)')
    print('\ttotal hyphens: (weighted)', project.dictionary.compute_total_hyphens())
    print('\tnumber of pattern levels:', len(project.patternset))
    
    for i, layer in enumerate(project.patternset):
        if i & 1 == 0:
            print((i+1), 'HYPHENATING patternset, num patterns:', len(layer))
        else:
            print((i+1), 'INHIBITING patternset, num patterns:', len(layer))
        print('\tTrained with: range %r, selector %r' % (layer.patlen_range, layer.selector))

    return 0


def main_train(args):
    
    project = Project.load(args.project)

    inhibiting = False
    if len(project.patternset) & 1:
        print('Training INHIBINTING pattern layer (level=%s)' % (len(project.patternset)+1))
        inhibiting = True
    else:
        print('Training HYPHENATION pattern layer (level=%s)' % (len(project.patternset)+1))

    patlen_rng = Range.parse(args.range)
    selector = Selector.parse(args.selector)

    print('\tpattern lengths:', patlen_rng)
    print('\tselector:', args.selector)
    
    total_hyphens = project.total_hyphens

    layer = Layer(patlen_rng, selector)
    layer_len = 0
    for patlen in stagger_range(patlen_rng.start, patlen_rng.end + 1):
        layer.train(patlen, project.dictionary, inhibiting, project.margins)
        print('Selected %s patterns of length %s' % (len(layer)-layer_len, patlen))
        layer_len = len(layer)

    # evaluate
    missed, false = layer.apply_to_dictionary(inhibiting, project.dictionary, margins=project.margins)

    print('Missed (weighted):', missed, '(%4.3f%%)' % (missed * 100 / (total_hyphens + 0.000001)))
    print('False (weighted):', false,   '(%4.3f%%)' % (false * 100 / (total_hyphens + 0.000001)))

    project.patternset.append(layer)

    #do_test(project, project.dictionary)

    if args.commit:
        project.save(args.project)
        print('...Committed!')

    return 0


def main_batchtrain(args):

    with codecs.open(args.specs, 'r', 'utf-8') as f:
        batches = eval(f.read())

    for rng, selector in batches:
        args.range = '%s-%s' % rng
        args.selector = '%s:%s:%s' % selector
        args.commit = True
        
        rc = main_train(args)
        if rc:
            print('Error:', rc)
            return rc
    
    return 0


def main_export(args):
    if os.path.exists(args.output):
        print('Pattern file already exists! Delete it first, or change the name. Pattern file: %s' % args.output)
        return -1
    
    project = Project.load(args.project)

    keys = set()
    for layer in project.patternset:
        keys.update(layer.keys())
    
    patts = []
    for key in sorted(keys):
        controls = [0] * (len(key) + 1)
        level = 0
        for layer in project.patternset:
            level += 1
            for index in layer.get(key, EMPTYSET):
                controls[index] = level

        out = []
        for i, c in enumerate(controls):
            if i > 0:
                out.append(key[i-1])
            if c > 0:
                out.append(str(c))

        patt = ''.join(out)
        patts.append(patt)

    num_patterns = 0
    num_exceptions = 0
    
    with codecs.open(args.output, 'w', 'utf-8') as f:
        f.write('\\patterns{\n')
        for patt in patts:
            f.write(patt + '\n')
            num_patterns += 1
        f.write('}\n')
        f.write('\\hyphenation{\n')
        for word, _, _, _ in do_test(project, project.dictionary):
            text = format_dictionary_word(word, project.dictionary[word])
            f.write(text + '\n')
            num_exceptions += 1
        f.write('}\n')
    
    print('Created TeX patterns file', args.output)
    print('Number of patterns:', num_patterns)
    print('Number of exceptions:', num_exceptions)
    
    return 0


def main_show_errors(args):
    project = Project.load(args.project)
    
    do_test(project, project.dictionary)
    
    return 0


def main_hyphenate(args):
    
    project = Project.load(args.project)

    with codecs.open(args.input or sys.stdin.fileno(), 'r', 'utf-8') as f:
        with codecs.open(args.output or sys.stdout.fileno(), 'w', 'utf-8') as out:

            for word in f:
                word = word.strip()
                if not word:
                    continue
    
                prediction = project.patterns.hyphenate(word, margins=project.margins) 

                s = format_dictionary_word(word, prediction)
                out.write(s + '\n')


def main_test(args):
    project = Project.load(args.project)

    dictionary = Dictionary.load(args.dictionary)

    errors = do_test(project, dictionary)
    if args.errors:
        with codecs.open(args.errors, 'w', 'utf-8') as f:
            for word, hyphens, missed, false in errors:
                f.write(format_dictionary_word(word, hyphens, missed, false) + '\n')

    return 0


def do_test(project, dictionary):

    total_hyphens = dictionary.compute_total_hyphens()

    num_missed = 0
    num_false = 0
    errors = []
    for word, hyphens in dictionary.items():
        prediction = project.patternset.hyphenate(word, margins=project.margins) 
        weight = dictionary.weights[word]

        err = False
        missed = hyphens - prediction
        false  = prediction - hyphens
        if missed:
            num_missed += sum(weight[x] for x in missed)
            err = True
        if false:
            num_false += sum(weight[x] for x in false)
            err = True

        if err:
            errors.append( (word, hyphens, missed, false) )

    print('Missed (weighted):', num_missed, '(%4.3f%%)' % (num_missed * 100 / (total_hyphens + 0.000001)))
    print('False (weighted):', num_false,   '(%4.3f%%)' % (num_false * 100 / (total_hyphens + 0.000001)))
    
    return errors


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generates TeX hyphenation patterns')
    parser.add_argument('project', help='Name of the project file')
    sub    = parser.add_subparsers(help='Commands', dest='cmd')
    
    # "new" command
    parser_new = sub.add_parser('new', help='Creates new hyphenation pattern project from dictionary')
    parser_new.add_argument('dictionary', help='Dictionary of hyphenated words (one word per line)')
    parser_new.add_argument('-m', '--margins', help='Hyphenation margins. If not set, will  be computed from the dictionary')
    
    # "show" command
    parser_show = sub.add_parser('show', help='Displays information about current hyphenation project')  # @UnusedVariable

    # "train" command
    parser_train = sub.add_parser('train', help='Trains next level of hyphenation patterns')
    parser_train.add_argument('-s', '--selector', default='1:5:10', help='triplet of numbers that control pattern selection. Format is: "good_weight:bad_weight:threshold"')
    parser_train.add_argument('-r', '--range', default='1,5', help='range of patterns lengths. Default is 1,5')
    parser_train.add_argument('-c', '--commit', default=False, action='store_true', help='If set, project is modified')

    # "batchtrain" command
    parser_batchtrain = sub.add_parser('batchtrain', help='Trains all levels from batch specs')
    parser_batchtrain.add_argument('-s', '--specs', help='file with batch training parameters specifications')

    # "export" command
    parser_export = sub.add_parser('export', help='Exports project as a set of TeX patterns')
    parser_export.add_argument('output', help='Name of the TeX pattern file to create')

    # "show_errors" command
    parser_show_errors = sub.add_parser('show_errors', help='Shows all errors')  # @UnusedVariable

    # "hyphenate" command
    parser_hyphenate = sub.add_parser('hyphenate', help='Hyphenates a list of words')
    parser_hyphenate.add_argument('-i', '--input', default=None, help='Input file with word list - one word per line. If not given, reads stdin.')
    parser_hyphenate.add_argument('-o', '--output', default=None, help='Output file with hyphenated words - one per line. If not given, writes to stdout.')

    # "teste" command
    parser_test = sub.add_parser('test', help='Test performance on an independent dictionary')
    parser_test.add_argument('dictionary', help='File name of a test dictionary')
    parser_test.add_argument('-e', '--errors', help='Optional file to write errors (for error analysis)')


    args = parser.parse_args()
    if args.cmd == 'new':
        parser.exit(main_new(args))
    elif args.cmd == 'show':
        parser.exit(main_show(args))
    elif args.cmd == 'train':
        parser.exit(main_train(args))
    elif args.cmd == 'export':
        parser.exit(main_export(args))
    elif args.cmd == 'show_errors':
        parser.exit(main_show_errors(args))
    elif args.cmd == 'hyphenate':
        parser.exit(main_hyphenate(args))
    elif args.cmd == 'batchtrain':
        parser.exit(main_batchtrain(args))
    elif args.cmd == 'test':
        parser.exit(main_test(args))
    else:
        parser.error('Command required')


if __name__ == '__main__':
    main()

'''

1. Dictionary load and save tools:
   A. load dictionary from file (optional missed and false hyphens are marked there)
   B. save dictionary to file

2. Pattern set load and save tools:
   A. Load TeX pattern set from file
   B. Save TeX pattern set to file
   C. Assign layers from one pattern set to another

Actions:

- apply patternset to a word
- apply patternset to every word in a dictionary and compute false and missed
- apply just one level of pattern to a word


# Dictionary
dictionary = Dictionary.load(filename)
dictionary.margins
dictionary.weights
dictionary.data
dictionary.keys

# chunker

# new project
project = Project(dictionary, margins=(1,1))

# new PatternLayer
layer = Layer()

# 

'''