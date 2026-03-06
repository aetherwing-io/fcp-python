# fcp-python

Python Code Intelligence FCP — an MCP server for querying and refactoring Python codebases through intent-level commands.

Wraps [pylsp](https://github.com/python-lsp/python-lsp-server) (python-lsp-server) with [rope](https://github.com/python-rope/rope) for refactoring.

## Install

```bash
uvx fcp-python
```

## Usage

```
python_session  ->  open /path/to/project
python_query    ->  find MyClass
python_query    ->  def my_function @file:main.py
python_query    ->  refs MyClass @file:models.py
python_query    ->  symbols src/main.py
python_query    ->  diagnose
python_query    ->  inspect MyClass
python_query    ->  callers process_data
python_query    ->  map
python_query    ->  unused
python          ->  rename Config Settings
python          ->  extract validate @file:server.py @lines:15-30
python          ->  import os @file:main.py @line:5
python_help     ->  (shows reference card)
```

## License

MIT
