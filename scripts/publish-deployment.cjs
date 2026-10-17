// Publish only after the test and multiarch image jobs have succeeded.
const fs = require('node:fs');

module.exports = async function publish({github, context, core}) {
  const repo = context.repo;
  const branch = 'deploy/production';
  const main = () => github.rest.git.getRef({...repo, ref: 'heads/main'});
  if ((await main()).data.object.sha !== context.sha) {
    core.info('A newer main commit exists; skipping this deployment.');
    return;
  }
  const source = fs.readFileSync('deploy/portainer-stack.yml', 'utf8');
  const placeholder = '  image: ${RSA_IMAGE:-research-slide-agent:local}';
  if (source.split(placeholder).length !== 2) {
    throw new Error('Expected exactly one runtime image in the stack.');
  }
  const image = `ghcr.io/${repo.owner}/${repo.repo}:${context.sha}`.toLowerCase();
  const content = source.replace(placeholder, `  image: ${image}`);
  let previous;
  try {
    previous = (await github.rest.git.getRef({...repo, ref: `heads/${branch}`})).data.object.sha;
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  const tree = (await github.rest.git.createTree({
    ...repo,
    tree: [{path: 'compose.yaml', mode: '100644', type: 'blob', content}],
  })).data.sha;
  if (previous) {
    const commit = (await github.rest.git.getCommit({...repo, commit_sha: previous})).data;
    if (commit.tree.sha === tree) {
      core.info('This deployment is already published.');
      return;
    }
  }
  const commit = (await github.rest.git.createCommit({
    ...repo,
    message: `Deploy ${context.sha}`,
    tree,
    parents: previous ? [previous] : [],
  })).data.sha;
  // Recheck immediately before publishing, and never force-push over another writer.
  if ((await main()).data.object.sha !== context.sha) {
    core.info('Main changed while preparing the deployment; skipping publication.');
    return;
  }
  if (previous) {
    await github.rest.git.updateRef({...repo, ref: `heads/${branch}`, sha: commit, force: false});
  } else {
    await github.rest.git.createRef({...repo, ref: `refs/heads/${branch}`, sha: commit});
  }
  core.info(`Published ${image} to ${branch}`);
};
