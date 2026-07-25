# Community platform pack — example

Fichier d'exemple pour tester la fonctionnalité **Pack Sources** de Romarr
(Settings → Platforms → Pack sources) sans avoir à créer un repo dédié.

`platform-pack-community.yaml` est un mirror de `builtin-2026.05.002.yaml`
augmenté de 6 plateformes supplémentaires :

- **Gen 8-9 home consoles** — `ps4`, `ps5`, `xbox-one`, `xbox-series`
- **Retro japonais** — `x68000`, `pc98`

`pack_version: 2026.07.100` — supérieur au builtin, donc accepté sans
conflit lexical. Aucun slug ne clash.

## Usage

Copier son URL raw dans Romarr :

```
http://<gitlab-host>/root/romarr/-/raw/<branch>/examples/community-pack/platform-pack-community.yaml
```

Ou pointer un `github_dir` sur le dossier :

```
http://<gitlab-host>/root/romarr/-/tree/<branch>/examples/community-pack
```

(la sync walker sur GitLab n'est pas encore implémentée — pour l'instant
utiliser le mode raw single-file. Le walker `api.github.com` ne couvre
que GitHub.com. Étendre à GitLab landera dans une itération future.)
