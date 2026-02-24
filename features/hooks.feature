Feature: Git Hooks for Quality Assurance and Collaboration
  As a contributor (human or AI agent)
  I want git hooks to verify my changes before I commit or push
  So that the repository remains clean, consistent, and stable

  Background:
    Given I have the repository cloned
    And I have installed the git hooks using "scripts/install-hooks.sh"

  Scenario: Human contributor commits code with syntax errors
    Given I am a human contributor
    And I have a file "bad_syntax.py" with content "def foo("
    When I stage "bad_syntax.py"
    And I attempt to commit with message "Add bad syntax"
    Then the commit should fail
    And I should see an error message indicating a syntax error
    And I should see instructions on how to fix it

  Scenario: Human contributor commits code with formatting issues
    Given I am a human contributor
    And I have a file "messy.py" with valid but unformatted python code
    When I stage "messy.py"
    And I attempt to commit with message "Add messy code"
    Then the commit should fail
    And I should see an error message from the linter
    And I should see a suggestion to run "black ."

  Scenario: Human contributor pushes to main branch directly
    Given I am on the "main" branch
    When I attempt to push to "origin main"
    Then the push should fail
    And I should see an error message discouraging direct pushes to main

  Scenario: AI Agent commits valid code
    Given I am an AI agent
    And I have a file "good.py" with valid and formatted content
    When I stage "good.py"
    And I attempt to commit with message "Add good feature"
    Then the commit should succeed

  Scenario: AI Agent encounters a linting error
    Given I am an AI agent
    And I have generated code with a linting violation
    When I stage the code
    And I attempt to commit
    Then the commit should fail
    And the output should contain the specific file and line number of the error
    And the output should be parseable (standard linter format)

  Scenario: Pre-push hook runs tests
    Given I have committed valid changes
    When I attempt to push to a feature branch
    Then the pre-push hook should trigger "scripts/run-tests.sh"
    And if tests pass, the push should succeed
    And if tests fail, the push should fail
