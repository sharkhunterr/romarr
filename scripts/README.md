# Scripts de Release et Déploiement Romarr

Ce dossier contient les scripts d'automatisation pour les releases, pushs Git
et déploiements Docker. Ils suivent le même principe que grabarr / pressarr /
ghostarr (template sharkhunterr).

> **Layout du dépôt** — le projet romarr est imbriqué dans `romarr/` sous la
> racine git. Ce `package.json`, ce dossier `scripts/` et le `.gitlab-ci.yml`
> vivent à la **racine git** ; les commandes `npm run …` se lancent donc depuis
> la racine git, pas depuis `romarr/`.

## 📦 Commandes de Release

### Release standard (GitLab uniquement)
```bash
npm run release              # Patch release (0.14.0 → 0.14.1)
npm run release:patch        # Équivalent à ci-dessus
npm run release:minor        # Minor release (0.14.0 → 0.15.0)
npm run release:major        # Major release (0.14.0 → 1.0.0)
```

**Ce que ça fait :**
- ✅ Bump version dans `package.json`, `romarr/pyproject.toml` et
  `romarr/src/romarr/__init__.py` (gardés en lock-step via `.versionrc.json`)
- ✅ Génère/met à jour `CHANGELOG.md`
- ✅ Crée un commit de release + un tag git `vX.Y.Z`
- ✅ Push vers GitLab avec les tags
- ✅ La CI GitLab (déclenchée par le tag) crée la release GitLab

### Release vers GitHub
```bash
npm run release:github       # Release GitLab + GitHub
```

### Release avec déploiement Docker
```bash
npm run release:deploy       # Release + trigger CI Docker deploy
npm run release:full         # Release GitLab + GitHub + Docker deploy
```

`release:full` ajoute `-o ci.variable="DEPLOY=true"` au push GitLab, ce qui
déclenche les stages `deploy` (build + push Docker Hub, mirror GitHub),
`release` (releases GitLab + GitHub) et `verify` du pipeline.

### Dry run
```bash
npm run release:dry          # Simule une release sans rien modifier
```

## 🚀 Commandes de Push
```bash
npm run push                 # Push vers GitLab (origin)
npm run push:github          # Push vers GitHub uniquement
npm run push:all             # Push vers GitLab ET GitHub
npm run push:tags            # Push uniquement les tags
```

## 🐳 Commandes Docker
```bash
npm run docker:build         # Build l'image localement
npm run docker:deploy        # Build + push vers Docker Hub (linux/amd64)
npm run docker:deploy:multi  # Build + push multi-plateforme (amd64 + arm64)
```

Le Dockerfile vit dans `romarr/Dockerfile` et son contexte de build est le
dossier `romarr/` — les scripts gèrent ça automatiquement.

## 🔄 Le pipeline GitLab CI

Le `.gitlab-ci.yml` (racine git) ne tourne **que sur les tags `vX.Y.Z`**.
Stages : `validate` (ruff) → `test` (pytest/uv) → `build` (sanity Docker) →
`publish` (registry GitLab, off par défaut) → `deploy` (Docker Hub + mirror
GitHub, gaté par `DEPLOY=true`) → `release` (releases GitLab + GitHub) →
`verify` (présence image + release).

### Variables CI à configurer (Settings → CI/CD → Variables)
| Variable | Usage |
|---|---|
| `DOCKER_HUB_USER` | login Docker Hub (= `sharkhunterr`) |
| `DOCKER_HUB_TOKEN` | token d'accès Docker Hub |
| `GITHUB_TOKEN` | PAT GitHub (mirror + releases) |
| `GITHUB_REPO` | `sharkhunterr/romarr` |

## 📝 Workflow complet

1. **Mettre à jour `GITHUB_RELEASES.md`** avec les notes de la prochaine version.
2. **Lancer la release** : `npm run release:full`.
3. **Vérifier** : releases GitLab, https://github.com/sharkhunterr/romarr/releases,
   https://hub.docker.com/r/sharkhunterr/romarr, et le pipeline GitLab CI.

## 📄 Structure des fichiers
```
scripts/
├── release.js           # Script de release principal
├── push.js              # Script de push Git
├── docker-deploy.js     # Script de déploiement Docker
├── pyproject-updater.js # Updater standard-version pour pyproject.toml
├── version-updater.js   # Updater standard-version pour __init__.py
├── render-assets.js     # Rendu des assets graphiques SVG → PNG
└── README.md            # Cette documentation
```

## 🆘 Dépannage

- **"glab/gh not found"** — les releases GitLab/GitHub côté CLI sont skippées ;
  la CI GitLab les crée de toute façon.
- **"remote not configured"** — `git remote add github https://github.com/sharkhunterr/romarr.git`.
- **"Working directory not clean"** — committez/stash avant une release.
