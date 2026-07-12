// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    { type: 'doc', id: 'index', label: 'Introduction' },
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: [
        { type: 'doc', id: 'start/install', label: 'Install' },
        { type: 'doc', id: 'start/quickstart', label: 'Quickstart' },
      ],
    },
    {
      type: 'category',
      label: 'Guide',
      collapsed: false,
      items: [
        { type: 'doc', id: 'guide/concepts', label: 'Concepts' },
        { type: 'doc', id: 'guide/stacking', label: 'Stacking' },
        { type: 'doc', id: 'guide/syncing', label: 'Syncing' },
        { type: 'doc', id: 'guide/submitting', label: 'Submitting' },
        { type: 'doc', id: 'guide/landing', label: 'Landing' },
        { type: 'doc', id: 'guide/editing', label: 'Editing' },
        { type: 'doc', id: 'guide/hooks', label: 'Hooks' },
        { type: 'doc', id: 'guide/scripting', label: 'Scripting' },
        { type: 'doc', id: 'guide/architecture', label: 'Architecture' },
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      collapsed: false,
      items: [
        { type: 'doc', id: 'reference/commands', label: 'Commands' },
        { type: 'doc', id: 'reference/config', label: 'Configuration' },
        { type: 'doc', id: 'reference/hooks', label: 'Hooks' },
        { type: 'doc', id: 'reference/exit-codes', label: 'Exit codes' },
        { type: 'doc', id: 'reference/json-output', label: 'JSON output' },
      ],
    },
  ],
};

module.exports = sidebars;
