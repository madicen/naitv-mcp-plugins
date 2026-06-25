# plugins/

This directory is a local development shortcut — you can point `install_plugin`
at files here while the separate `madicen/naitv-plugins` repo is not yet live:

```
install_plugin(source="./plugins/loop-engineering-go.json")
```

The canonical home for these files is the **`naitv-plugins/`** directory at the
root of this repo (staged for extraction to `github.com/madicen/naitv-plugins`).
Once that repo is published, install by name instead:

```
install_plugin(source="loop-engineering-go")
```
