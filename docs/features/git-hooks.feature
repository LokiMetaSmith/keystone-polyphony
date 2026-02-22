Feature: Git Hooks for Human/Agent Collaboration

  As a contributor to Keystone Polyphony
  I want robust git hooks
  So that the repository remains clean and common errors are caught early.

  Background:
    Given the git hooks are installed via scripts/install-hooks.sh

  Scenario: Automatically normalize whitespace on commit
    Given I am on a feature branch
    And I have staged a file with trailing whitespace
    When I run "git commit"
    Then the trailing whitespace should be removed from the staged content
    And the commit should succeed

  Scenario: Block commits to main branch
    Given I am on the "main" branch
    When I run "git commit"
    Then the commit should be blocked
    And I should see "[ERROR] Committing directly to 'main' is discouraged"

  Scenario: Allow commits to main branch with override
    Given I am on the "main" branch
    And I set the environment variable "ALLOW_MAIN_COMMIT=1"
    When I run "git commit"
    Then the commit should succeed

  Scenario: Catch shell syntax errors
    Given I am on a feature branch
    And I have staged a ".sh" file with a syntax error
    When I run "git commit"
    Then the commit should be blocked
    And I should see "[ERROR] Shell syntax error"

  Scenario: Block pushing to main branch
    Given I am pushing to "origin/main"
    When the pre-push hook runs
    Then the push should be blocked
    And I should see "[ERROR] Pushing directly to 'main' is discouraged"

  Scenario: Run tests on push
    Given I am on a feature branch
    And I am pushing to "origin"
    When the pre-push hook runs
    Then it should execute "scripts/run-tests.sh"
    And if tests pass, the push should succeed
    And if tests fail, the push should be blocked
