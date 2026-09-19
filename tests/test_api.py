# -*- coding: utf-8 -*-
"""
    jinja2.testsuite.api
    ~~~~~~~~~~~~~~~~~~~~

    Tests the public API and related stuff.

    :copyright: (c) 2017 by the Jinja Team.
    :license: BSD, see LICENSE for more details.
"""
import os
import pickle
import tempfile
import shutil

import pytest
from jinja2 import Environment, Undefined, DebugUndefined, \
     StrictUndefined, ChainableUndefined, UndefinedError, meta, \
     is_undefined, Template, DictLoader, make_logging_undefined
from jinja2.compiler import CodeGenerator
from jinja2.runtime import Context, missing
from jinja2.utils import Cycler


@pytest.mark.api
@pytest.mark.extended
class TestExtendedAPI(object):

    def test_item_and_attribute(self, env):
        from jinja2.sandbox import SandboxedEnvironment

        for env in Environment(), SandboxedEnvironment():
            # the |list is necessary for python3
            tmpl = env.from_string('{{ foo.items()|list }}')
            assert tmpl.render(foo={'items': 42}) == "[('items', 42)]"
            tmpl = env.from_string('{{ foo|attr("items")()|list }}')
            assert tmpl.render(foo={'items': 42}) == "[('items', 42)]"
            tmpl = env.from_string('{{ foo["items"] }}')
            assert tmpl.render(foo={'items': 42}) == '42'

    def test_finalizer(self, env):
        def finalize_none_empty(value):
            if value is None:
                value = u''
            return value
        env = Environment(finalize=finalize_none_empty)
        tmpl = env.from_string('{% for item in seq %}|{{ item }}{% endfor %}')
        assert tmpl.render(seq=(None, 1, "foo")) == '||1|foo'
        tmpl = env.from_string('<{{ none }}>')
        assert tmpl.render() == '<>'

    def test_cycler(self, env):
        items = 1, 2, 3
        c = Cycler(*items)
        for item in items + items:
            assert c.current == item
            assert next(c) == item
        next(c)
        assert c.current == 2
        c.reset()
        assert c.current == 1

    def test_cycler_nextmethod(self, env):
        items = 1, 2, 3
        c = Cycler(*items)
        for item in items + items:
            assert c.current == item
            assert c.next() == item
        c.next()
        assert c.current == 2
        c.reset()
        assert c.current == 1

    def test_expressions(self, env):
        expr = env.compile_expression("foo")
        assert expr() is None
        assert expr(foo=42) == 42
        expr2 = env.compile_expression("foo", undefined_to_none=False)
        assert is_undefined(expr2())

        expr = env.compile_expression("42 + foo")
        assert expr(foo=42) == 84

    def test_template_passthrough(self, env):
        t = Template('Content')
        assert env.get_template(t) is t
        assert env.select_template([t]) is t
        assert env.get_or_select_template([t]) is t
        assert env.get_or_select_template(t) is t

    def test_autoescape_autoselect(self, env):
        def select_autoescape(name):
            if name is None or '.' not in name:
                return False
            return name.endswith('.html')
        env = Environment(autoescape=select_autoescape,
                          loader=DictLoader({
                                                'test.txt':     '{{ foo }}',
                                                'test.html':    '{{ foo }}'
                                            }))
        t = env.get_template('test.txt')
        assert t.render(foo='<foo>') == '<foo>'
        t = env.get_template('test.html')
        assert t.render(foo='<foo>') == '&lt;foo&gt;'
        t = env.from_string('{{ foo }}')
        assert t.render(foo='<foo>') == '<foo>'


@pytest.mark.api
@pytest.mark.meta
class TestMeta(object):

    def test_find_undeclared_variables(self, env):
        ast = env.parse('{% set foo = 42 %}{{ bar + foo }}')
        x = meta.find_undeclared_variables(ast)
        assert x == set(['bar'])

        ast = env.parse('{% set foo = 42 %}{{ bar + foo }}'
                        '{% macro meh(x) %}{{ x }}{% endmacro %}'
                        '{% for item in seq %}{{ muh(item) + meh(seq) }}'
                        '{% endfor %}')
        x = meta.find_undeclared_variables(ast)
        assert x == set(['bar', 'seq', 'muh'])

    def test_find_refererenced_templates(self, env):
        ast = env.parse('{% extends "layout.html" %}{% include helper %}')
        i = meta.find_referenced_templates(ast)
        assert next(i) == 'layout.html'
        assert next(i) is None
        assert list(i) == []

        ast = env.parse('{% extends "layout.html" %}'
                        '{% from "test.html" import a, b as c %}'
                        '{% import "meh.html" as meh %}'
                        '{% include "muh.html" %}')
        i = meta.find_referenced_templates(ast)
        assert list(i) == ['layout.html', 'test.html', 'meh.html', 'muh.html']

    def test_find_included_templates(self, env):
        ast = env.parse('{% include ["foo.html", "bar.html"] %}')
        i = meta.find_referenced_templates(ast)
        assert list(i) == ['foo.html', 'bar.html']

        ast = env.parse('{% include ("foo.html", "bar.html") %}')
        i = meta.find_referenced_templates(ast)
        assert list(i) == ['foo.html', 'bar.html']

        ast = env.parse('{% include ["foo.html", "bar.html", foo] %}')
        i = meta.find_referenced_templates(ast)
        assert list(i) == ['foo.html', 'bar.html', None]

        ast = env.parse('{% include ("foo.html", "bar.html", foo) %}')
        i = meta.find_referenced_templates(ast)
        assert list(i) == ['foo.html', 'bar.html', None]


@pytest.mark.api
@pytest.mark.streaming
class TestStreaming(object):

    def test_basic_streaming(self, env):
        tmpl = env.from_string("<ul>{% for item in seq %}<li>{{ loop.index "
                               "}} - {{ item }}</li>{%- endfor %}</ul>")
        stream = tmpl.stream(seq=list(range(4)))
        assert next(stream) == '<ul>'
        assert next(stream) == '<li>1 - 0</li>'
        assert next(stream) == '<li>2 - 1</li>'
        assert next(stream) == '<li>3 - 2</li>'
        assert next(stream) == '<li>4 - 3</li>'
        assert next(stream) == '</ul>'

    def test_buffered_streaming(self, env):
        tmpl = env.from_string("<ul>{% for item in seq %}<li>{{ loop.index "
                               "}} - {{ item }}</li>{%- endfor %}</ul>")
        stream = tmpl.stream(seq=list(range(4)))
        stream.enable_buffering(size=3)
        assert next(stream) == u'<ul><li>1 - 0</li><li>2 - 1</li>'
        assert next(stream) == u'<li>3 - 2</li><li>4 - 3</li></ul>'

    def test_streaming_behavior(self, env):
        tmpl = env.from_string("")
        stream = tmpl.stream()
        assert not stream.buffered
        stream.enable_buffering(20)
        assert stream.buffered
        stream.disable_buffering()
        assert not stream.buffered

    def test_dump_stream(self, env):
        tmp = tempfile.mkdtemp()
        try:
            tmpl = env.from_string(u"\u2713")
            stream = tmpl.stream()
            stream.dump(os.path.join(tmp, 'dump.txt'), 'utf-8')
            with open(os.path.join(tmp, 'dump.txt'), 'rb') as f:
                assert f.read() == b'\xe2\x9c\x93'
        finally:
            shutil.rmtree(tmp)


class CustomChainableUndefined(ChainableUndefined):
    __slots__ = ()

    def __str__(self):
        return u'<%s>' % (self._undefined_name or 'undefined')


@pytest.mark.api
@pytest.mark.undefined
class TestUndefined(object):

    def test_stopiteration_is_undefined(self):
        def test():
            raise StopIteration()
        t = Template('A{{ test() }}B')
        assert t.render(test=test) == 'AB'
        t = Template('A{{ test().missingattribute }}B')
        pytest.raises(UndefinedError, t.render, test=test)

    def test_undefined_and_special_attributes(self):
        try:
            Undefined('Foo').__dict__
        except AttributeError:
            pass
        else:
            assert False, "Expected actual attribute error"

    def test_logging_undefined(self):
        _messages = []

        class DebugLogger(object):
            def warning(self, msg, *args):
                _messages.append('W:' + msg % args)

            def error(self, msg, *args):
                _messages.append('E:' + msg % args)

        logging_undefined = make_logging_undefined(DebugLogger())
        env = Environment(undefined=logging_undefined)
        assert env.from_string('{{ missing }}').render() == u''
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing.attribute }}').render)
        assert env.from_string('{{ missing|list }}').render() == '[]'
        assert env.from_string('{{ missing is not defined }}').render() \
            == 'True'
        assert env.from_string('{{ foo.missing }}').render(foo=42) == ''
        assert env.from_string('{{ not missing }}').render() == 'True'
        assert _messages == [
            'W:Template variable warning: missing is undefined',
            "E:Template variable error: 'missing' is undefined",
            'W:Template variable warning: missing is undefined',
            'W:Template variable warning: int object has no attribute missing',
            'W:Template variable warning: missing is undefined',
        ]

    def test_default_undefined(self):
        env = Environment(undefined=Undefined)
        assert env.from_string('{{ missing }}').render() == u''
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing.attribute }}').render)
        assert env.from_string('{{ missing|list }}').render() == '[]'
        assert env.from_string('{{ missing is not defined }}').render() \
            == 'True'
        assert env.from_string('{{ foo.missing }}').render(foo=42) == ''
        assert env.from_string('{{ not missing }}').render() == 'True'
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing - 1}}').render)

    def test_debug_undefined(self):
        env = Environment(undefined=DebugUndefined)
        assert env.from_string('{{ missing }}').render() == '{{ missing }}'
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing.attribute }}').render)
        assert env.from_string('{{ missing|list }}').render() == '[]'
        assert env.from_string('{{ missing is not defined }}').render() \
            == 'True'
        assert env.from_string('{{ foo.missing }}').render(foo=42) \
            == u"{{ no such element: int object['missing'] }}"
        assert env.from_string('{{ not missing }}').render() == 'True'

    def test_strict_undefined(self):
        env = Environment(undefined=StrictUndefined)
        pytest.raises(UndefinedError, env.from_string('{{ missing }}').render)
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing.attribute }}').render)
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing|list }}').render)
        assert env.from_string('{{ missing is not defined }}').render() \
            == 'True'
        pytest.raises(UndefinedError,
                      env.from_string('{{ foo.missing }}').render, foo=42)
        pytest.raises(UndefinedError,
                      env.from_string('{{ not missing }}').render)
        assert env.from_string('{{ missing|default("default", true) }}')\
            .render() == 'default'

    def test_indexing_gives_undefined(self):
        t = Template("{{ var[42].foo }}")
        pytest.raises(UndefinedError, t.render, var=0)

    def test_chainable_undefined(self):
        env = Environment(undefined=ChainableUndefined)
        # attribute and item access can be chained and mixed
        assert env.from_string('{{ missing.user.address.city }}')\
            .render() == u''
        assert env.from_string("{{ missing['user']['address'] }}")\
            .render() == u''
        assert env.from_string("{{ missing.user['address'].city }}")\
            .render() == u''
        # the chain always returns the very same undefined object
        undefined = env.undefined(name='missing')
        assert undefined.user.address['city'] is undefined
        # printing, boolean tests and iteration behave like the
        # default undefined
        assert env.from_string('{{ not missing.user }}').render() == 'True'
        assert env.from_string('{{ missing is not defined }}').render() \
            == 'True'
        assert env.from_string('{{ missing.user is not defined }}')\
            .render() == 'True'
        assert env.from_string('{{ missing.user|list }}').render() == '[]'
        assert env.from_string('{{ missing.user|length }}').render() == '0'
        assert env.from_string(
            '{% for item in missing.user %}{{ item }}{% endfor %}'
        ).render() == u''
        # everything that is not allowed for the default undefined keeps
        # raising an undefined error
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing.user + 1 }}').render)
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing.user < 1 }}').render)
        pytest.raises(UndefinedError,
                      env.from_string('{{ missing.user() }}').render)

    def test_chainable_undefined_error_message(self):
        # the originally missing name is retained for the error message
        try:
            ChainableUndefined(name='foo').bar['baz'] + 1
        except UndefinedError as e:
            assert e.message == "'foo' is undefined"
        else:
            assert False, 'expected exception'

    def test_chainable_undefined_default_filter(self):
        env = Environment(undefined=ChainableUndefined)
        tmpl = env.from_string(
            "{{ missing.user.address.city|default('Berlin') }}")
        assert tmpl.render() == 'Berlin'
        tmpl = env.from_string("{{ user.address.city|default('Berlin') }}")
        assert tmpl.render(user={'address': {'city': 'Paris'}}) == 'Paris'
        assert tmpl.render() == 'Berlin'

    def test_chainable_undefined_missing_levels(self):
        env = Environment(undefined=ChainableUndefined)
        tmpl = env.from_string("{{ user.address['city']|default('n/a') }}")
        # the variable itself is missing
        assert tmpl.render() == 'n/a'
        # the attribute of an existing object is missing
        assert tmpl.render(user={}) == 'n/a'
        # the item of an existing object is missing
        assert tmpl.render(user={'address': {}}) == 'n/a'
        # nothing is missing
        assert tmpl.render(user={'address': {'city': 'Paris'}}) == 'Paris'

    def test_chainable_undefined_private_attributes(self):
        undefined = ChainableUndefined(name='missing')
        # private attributes are not swallowed by the chain
        pytest.raises(AttributeError, lambda: undefined._private)
        pytest.raises(AttributeError, lambda: undefined.__deepcopy__)
        assert not hasattr(undefined, '__getnewargs__')
        # the actual private attributes of the undefined are untouched
        assert undefined._undefined_name == 'missing'
        assert undefined._undefined_exception is UndefinedError

    def test_chainable_undefined_custom_subclass(self):
        env = Environment(undefined=CustomChainableUndefined)
        assert env.from_string('{{ missing.user.address }}').render() \
            == '<missing>'
        assert env.from_string(
            "{{ missing.user.address|default('n/a') }}").render() == 'n/a'
        # the chain returns instances of the subclass
        undefined = env.undefined(name='missing')
        chained = undefined.user['address']
        assert chained is undefined
        assert isinstance(chained, CustomChainableUndefined)
        # and the subclass stays picklable
        clone = pickle.loads(pickle.dumps(undefined))
        assert isinstance(clone, CustomChainableUndefined)
        assert clone._undefined_name == 'missing'
        assert clone.user.address is clone

    def test_chainable_undefined_pickle(self):
        undefined = ChainableUndefined(name='missing')
        clone = pickle.loads(pickle.dumps(undefined))
        assert clone._undefined_name == 'missing'
        assert clone._undefined_obj is missing
        assert clone._undefined_hint is None
        assert clone._undefined_exception is UndefinedError
        # still chainable after unpickling
        assert clone.user['address'] is clone
        assert str(clone.user) == u''
        pytest.raises(UndefinedError, lambda: clone.user + 1)

    def test_chainable_undefined_pickle_with_details(self):
        undefined = ChainableUndefined(obj={'user': 1}, name='address',
                                       hint='the hint')
        clone = pickle.loads(pickle.dumps(undefined))
        assert clone._undefined_obj == {'user': 1}
        assert clone._undefined_name == 'address'
        assert clone._undefined_hint == 'the hint'

    def test_none_gives_proper_error(self):
        try:
            Environment().getattr(None, 'split')()
        except UndefinedError as e:
            assert e.message == "'None' has no attribute 'split'"
        else:
            assert False, 'expected exception'

    def test_object_repr(self):
        try:
            Undefined(obj=42, name='upper')()
        except UndefinedError as e:
            assert e.message == "'int object' has no attribute 'upper'"
        else:
            assert False, 'expected exception'


@pytest.mark.api
@pytest.mark.lowlevel
class TestLowLevel(object):

    def test_custom_code_generator(self):
        class CustomCodeGenerator(CodeGenerator):
            def visit_Const(self, node, frame=None):
                # This method is pure nonsense, but works fine for testing...
                if node.value == 'foo':
                    self.write(repr('bar'))
                else:
                    super(CustomCodeGenerator, self).visit_Const(node, frame)

        class CustomEnvironment(Environment):
            code_generator_class = CustomCodeGenerator

        env = CustomEnvironment()
        tmpl = env.from_string('{% set foo = "foo" %}{{ foo }}')
        assert tmpl.render() == 'bar'

    def test_custom_context(self):
        class CustomContext(Context):
            def resolve_or_missing(self, key):
                return 'resolve-' + key

        class CustomEnvironment(Environment):
            context_class = CustomContext

        env = CustomEnvironment()
        tmpl = env.from_string('{{ foo }}')
        assert tmpl.render() == 'resolve-foo'
