#!/usr/bin/env node
/**
 * Docker Hub deployment script for Romarr
 *
 * Features:
 * - Build and push Docker image to Docker Hub
 * - Tag with version and 'latest'
 * - Support for multi-platform builds
 *
 * Usage:
 *   npm run docker:build          # Build locally
 *   npm run docker:deploy         # Build and push to Docker Hub
 *   npm run docker:deploy:multi   # Multi-platform build and push
 *
 * NOTE on repo layout: the romarr project is nested in ``romarr/``
 * under the git root. The Dockerfile lives at ``romarr/Dockerfile``
 * and its COPY steps are relative to ``romarr/`` — so the build
 * context is ``romarr/``, not ``.``.
 */

const { execSync } = require('child_process');
const fs = require('fs');

// Parse command line arguments
const args = process.argv.slice(2);
const options = {
  push: args.includes('--push'),
  multiPlatform: args.includes('--multi-platform'),
  latest: !args.includes('--no-latest'),
  dryRun: args.includes('--dry-run'),
  buildOnly: args.includes('--build-only'),
};

// Romarr project lives one directory down from the git root.
const PROJECT_DIR = 'romarr';
const DOCKERFILE = `${PROJECT_DIR}/Dockerfile`;
const BUILD_CONTEXT = PROJECT_DIR;

// Get package version
function getVersion() {
  const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
  return pkg.version;
}

// Get Docker Hub info from package.json
function getDockerConfig() {
  const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
  return {
    image: pkg.config?.dockerImage || 'sharkhunterr/romarr',
    registry: pkg.config?.dockerRegistry || 'docker.io',
  };
}

// Execute command
function exec(command, description) {
  console.log(`\n🐳 ${description}...`);
  if (options.dryRun) {
    console.log(`   [DRY RUN] ${command}`);
    return '';
  }
  try {
    const output = execSync(command, { encoding: 'utf8', stdio: 'inherit' });
    console.log('   ✅ Done');
    return output;
  } catch (error) {
    console.error(`   ❌ Failed: ${description}`);
    process.exit(1);
  }
}

function main() {
  console.log('🐳 Romarr Docker Deployment Script\n');
  console.log('Options:', options);

  const version = getVersion();
  const dockerConfig = getDockerConfig();
  const { image, registry } = dockerConfig;

  console.log(`\n📦 Version: ${version}`);
  console.log(`🐋 Image: ${registry}/${image}`);

  // Check if Docker is running
  try {
    execSync('docker info', { stdio: 'ignore' });
  } catch {
    console.error('❌ Docker is not running. Please start Docker and try again.');
    process.exit(1);
  }

  const tags = [
    `${registry}/${image}:${version}`,
    `${registry}/${image}:v${version}`,
  ];

  if (options.latest) {
    tags.push(`${registry}/${image}:latest`);
  }

  console.log(`\n🏷️  Tags: ${tags.join(', ')}`);

  if (options.multiPlatform) {
    // Multi-platform build using buildx
    console.log('\n🌍 Building for multiple platforms (linux/amd64, linux/arm64)...');

    // Create/use buildx builder
    exec(
      'docker buildx create --use --name romarr-builder 2>/dev/null || docker buildx use romarr-builder',
      'Setting up buildx builder'
    );

    const tagArgs = tags.map(t => `-t ${t}`).join(' ');
    const pushFlag = options.push ? '--push' : '--load';

    exec(
      `docker buildx build --platform linux/amd64,linux/arm64 ${tagArgs} ${pushFlag} -f ${DOCKERFILE} ${BUILD_CONTEXT}`,
      'Building multi-platform image'
    );

  } else {
    // Single platform build
    const tagArgs = tags.map(t => `-t ${t}`).join(' ');

    exec(
      `docker build ${tagArgs} -f ${DOCKERFILE} ${BUILD_CONTEXT}`,
      'Building Docker image'
    );

    // Push if requested
    if (options.push && !options.buildOnly) {
      for (const tag of tags) {
        exec(`docker push ${tag}`, `Pushing ${tag}`);
      }
    }
  }

  console.log('\n✅ Docker deployment completed successfully!');

  if (options.push) {
    console.log(`\n🔗 Docker Hub: https://hub.docker.com/r/${image}`);
    console.log(`\n📥 Pull with: docker pull ${registry}/${image}:${version}`);
  } else {
    console.log(`\n💡 To push to Docker Hub, run: npm run docker:deploy`);
  }
}

// Run
main();
