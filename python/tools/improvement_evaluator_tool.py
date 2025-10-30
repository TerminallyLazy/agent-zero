# python/tools/improvement_evaluator_tool.py
from python.helpers.tool import Tool, Response
import json
import os


class ImprovementEvaluator(Tool):
    """
    Tool for evaluating whether a code modification improved the agent's performance.

    Compares agent behavior before and after a patch to assess:
    - Performance impact
    - Improvements gained
    - Regressions introduced
    - Overall score (-2 to +2)
    """

    async def execute(self, **kwargs) -> Response:
        # Collect all context needed for evaluation
        before_code = self.args.get('before_code', '')
        before_tools = self.args.get('before_tools', '')
        model_patch = self.args.get('model_patch', '')
        patch_description = self.args.get('patch_description', '')

        # Test case context
        problem_id = self.args.get('problem_id', '')
        problem_statement = self.args.get('problem_statement', '')
        ground_truth_solution = self.args.get('ground_truth_solution', '')
        test_cases = self.args.get('test_cases', '')

        # Performance data
        before_log = self.args.get('before_log', '')
        before_prediction = self.args.get('before_prediction', '')
        before_test_results = self.args.get('before_test_results', '')

        after_log = self.args.get('after_log', '')
        after_prediction = self.args.get('after_prediction', '')
        after_test_results = self.args.get('after_test_results', '')

        # Build evaluation prompt
        prompt = self.agent.read_prompt(
            "hgm.evaluate_improvement.md",
            before_code=before_code,
            before_tools=before_tools,
            model_patch=model_patch,
            patch_description=patch_description,
            problem_id=problem_id,
            problem_statement=problem_statement,
            ground_truth_solution=ground_truth_solution,
            test_cases=test_cases,
            before_log=before_log,
            before_prediction=before_prediction,
            before_test_results=before_test_results,
            after_log=after_log,
            after_prediction=after_prediction,
            after_test_results=after_test_results
        )

        # Get LLM evaluation
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=prompt)]

        llm = self.agent.get_utility_model()
        response = await llm.ainvoke(messages)

        # Parse JSON response
        try:
            content = response.content

            # Extract JSON from response (might be wrapped in markdown)
            if '```json' in content:
                json_start = content.index('```json') + 7
                json_end = content.rindex('```')
                content = content[json_start:json_end].strip()
            elif '```' in content:
                json_start = content.index('```') + 3
                json_end = content.rindex('```')
                content = content[json_start:json_end].strip()

            # Parse evaluation
            evaluation = json.loads(content)

            # Validate required fields
            required_fields = [
                'performance_impact',
                'improvements',
                'regressions',
                'overall_score',
                'confidence',
                'reasoning',
                'recommendation'
            ]

            for field in required_fields:
                if field not in evaluation:
                    evaluation[field] = f"[Error: {field} not provided]"

            # Ensure improvements/regressions are lists
            if not isinstance(evaluation['improvements'], list):
                evaluation['improvements'] = [str(evaluation['improvements'])]
            if not isinstance(evaluation['regressions'], list):
                evaluation['regressions'] = [str(evaluation['regressions'])]

            # Format response
            result = self._format_evaluation(evaluation)

            return Response(
                message=result,
                break_loop=False
            )

        except (json.JSONDecodeError, ValueError) as e:
            # Return error with raw response
            error_result = f"""Error parsing evaluation response: {str(e)}

Raw response:
{response.content}"""

            return Response(
                message=error_result,
                break_loop=False
            )

    def _format_evaluation(self, evaluation: dict) -> str:
        """Format evaluation results as readable text"""
        score = evaluation['overall_score']
        confidence = evaluation['confidence']

        # Determine score interpretation
        if score >= 1.5:
            interpretation = "Major Improvement ✓✓"
        elif score >= 0.5:
            interpretation = "Minor Improvement ✓"
        elif score >= -0.5:
            interpretation = "No Significant Change ~"
        elif score >= -1.5:
            interpretation = "Minor Regression ✗"
        else:
            interpretation = "Major Regression ✗✗"

        result = f"""# Improvement Evaluation Results

## Overall Assessment: {interpretation}
**Score**: {score}/2.0 (Confidence: {confidence})

## Performance Impact
{evaluation['performance_impact']}

## Improvements Identified ({len(evaluation['improvements'])})
"""
        for i, improvement in enumerate(evaluation['improvements'], 1):
            result += f"{i}. {improvement}\n"

        result += f"\n## Regressions Detected ({len(evaluation['regressions'])})\n"
        if not evaluation['regressions'] or evaluation['regressions'] == []:
            result += "None identified\n"
        else:
            for i, regression in enumerate(evaluation['regressions'], 1):
                result += f"{i}. {regression}\n"

        result += f"""
## Reasoning
{evaluation['reasoning']}

## Recommendation
{evaluation['recommendation']}

---

**Raw Evaluation Data**:
```json
{json.dumps(evaluation, indent=2)}
```
"""

        return result

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading="icon://analytics Improvement Evaluation",
            content="",
            kvps=self.args,
        )
