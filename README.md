Stacking PR Utility Tool.

Problem: Many a times, you have big PRs, and you want to split them into multiple individual small PRs so I can review without getting lost.

Issues: Stacking PRs is a PITA. Too much cardinality makes it difficult, plus testing everything together also is a PITA. How do you define that division and unblock yourself. Rebase hell.

Existing solution: Two types: Saas Tools ; Local CLI Stuff.


Problem Domain:
Git is a VCS, generally used for source code. You create a branch, work on it, and then merge it back to master. Issue is most of engineering hours are spent in reviews, and if the PR is big it requires a lot of effort from reviewer to make sure everything is fine. The idea for a stacked diff is to have 1 commit = 1 PR.


Issue is: Division of work, maintaining context of all the changes across the stacks, pushing things to GH. There are rules for some repos on what goes in a PR. How do you define that across the stack and what goes in one PR?


Solution: Local CLI Tool that helps solve the core problem associated with stacked PRs. Also a screen like lazy git where they can visualize what their stack looks like. If we solve the core problem first, building on top of it is easier.

Things to have out of the box:
1) Cascading Rebase
2) Arrange pull requests in an ordered stack and merge them all in one click(this is actually important - but this should be at gh level from representation, but we can also have a command in our thing).
3) Create stack, perform cascading rebases, push branches, create PRs
4) Create, Modify, Submit, Review the stack.
5) testing everything at once?????
6) Easier articat, but also easier constructs to make this maintainable.
7) Representation layer, at CLI or local website, I need to thing about that.
