// @ts-check
const { themes: prismThemes } = require('prism-react-renderer');

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'arc',
  tagline: 'Stacked PRs without the manual overhead',
  favicon: 'img/favicon.svg',

  stylesheets: [
    {
      href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap',
      type: 'text/css',
    },
  ],

  url: 'https://arc-pr-docs.netlify.app',
  baseUrl: '/',

  organizationName: 'yash-srivastava19',
  projectName: 'arc-stack',

  onBrokenLinks: 'throw',

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
          editUrl: 'https://github.com/yash-srivastava19/arc-stack/edit/main/',
          exclude: [
            // Internal planning docs — not for public site
            'superpowers/**',
            'developer/**',
            'features/**',
            'BACKLOG.md',
            // Stale Sphinx-era files superseded by start/ and guide/
            'quickstart.md',
            'install.md',
            'guides/**',
          ],
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: 'arc',
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'docs',
            label: 'Docs',
            position: 'left',
          },
          {
            href: 'https://github.com/yash-srivastava19/arc-stack',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'light',
        links: [],
        copyright: `arc · <a href="https://github.com/yash-srivastava19/arc-stack">GitHub</a>`,
      },
      prism: {
        theme: prismThemes.github,
        additionalLanguages: ['bash', 'json', 'python'],
      },
      colorMode: {
        defaultMode: 'light',
        disableSwitch: true,
        respectPrefersColorScheme: false,
      },
    }),
};

module.exports = config;
