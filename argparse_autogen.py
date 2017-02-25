import argparse
import inspect
import re


def parse_docstring(docstring):
    docstring = docstring or ''
    lines = docstring.split('\n')
    description = []
    while lines:
        line = lines[0].strip()
        lines = lines[1:]
        if not line:
            continue

        if line.startswith(':'):
            lines.insert(0, line)
            break

        description.append(line)

    params = []

    while lines:
        line = lines[0].strip()
        lines = lines[1:]
        if not line:
            continue

        if not line.startswith(':') and params:
            params[-1]['description'] += '\n' + line.strip()
            continue

        match = re.match('^:param\s+(?P<type>.+?)?(?(type)\s+|)(?P<name>.+?):(?P<description>.+)?', line)
        if match:
            params.append(match.groupdict())

    return '\n'.join(description), params


def autospec(parser, func, argument_overrides=None):
    docstring = inspect.getdoc(func) or inspect.getcomments(func)
    parser.description, params_docs = parse_docstring(docstring)

    signature = inspect.signature(func)
    for param_name, param in signature.parameters.items():
        if param_name == 'self' or param_name == 'cls':
            continue

        kwargs = dict(
            action='store',
            help=param_name
        )

        for param_doc in params_docs:
            if param_doc['name'] == param_name:
                kwargs['help'] = param_doc['description']

        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            kwargs['nargs'] = '*'
            kwargs['help'] = 'Optional keyword arguments. Specify them as key=value'

        if param.default is not inspect._empty:
            param_name = '--' + param_name
            kwargs['default'] = param.default

        if isinstance(param.default, bool):
            if param.default:
                kwargs['action'] = 'store_false'
            else:
                kwargs['action'] = 'store_true'

        parser.add_argument(param_name, **kwargs)


class EndpointParser(argparse.ArgumentParser):
    subparsers = None
    internal_keys = {'__func__', '__endpoint__'}

    def clear_internal_keys(self, args):
        """
        :param dict|argparse.Namespace args:
        :rtype: dict
        """
        if not isinstance(args, dict):
            args = vars(args)
        for key in self.internal_keys:
            args.pop(key, None)
        kwargs = args.pop('kwargs', [])
        for item in kwargs:
            key, value = item.split('=')
            args[key] = value
        return args

    def add_subparsers(self, **kwargs):
        self.subparsers = super(EndpointParser, self).add_subparsers(**kwargs)
        return self.subparsers

    # noinspection PyProtectedMember
    def get_endpoint_parser(self, path):
        """
        :param str|list|tuple path:
        :rtype: argparse.ArgumentParser
        """
        if not isinstance(path, (list, tuple)):
            path = path.split('.')
            if len(path) == 1 and path[0]:
                path = path[0].split(' ')
            elif len(path) == 1 and not path[0]:
                path = []

        if not path:
            return self

        parser = self

        for key in path:
            if parser.subparsers is None:
                parser.add_subparsers()
            if key in parser.subparsers._name_parser_map:
                parser = parser.subparsers._name_parser_map[key]
            else:
                parser = parser.subparsers.add_parser(key)

        parser.path = path

        return parser

    def add_endpoint(self, path, func=None, autospec=True, argument_overrides=None):
        parser = self.get_endpoint_parser(path)

        if func:
            if autospec:
                globals()['autospec'](parser, func, argument_overrides=argument_overrides)
            parser.set_defaults(__func__=func)

        parser.set_defaults(__endpoint__=path)

        return parser

    def parse_and_call(self, *args, **kwargs):
        args = self.parse_args(*args, **kwargs)
        return self.call(args)

    def call(self, args):
        if not hasattr(args, '__func__'):
            self.error('Invalid endpoint')

        func = args.__func__
        args = self.clear_internal_keys(args)

        return func(**args)