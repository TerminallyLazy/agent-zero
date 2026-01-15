import asyncio

from python.helpers.tool import Tool, Response
from python.helpers.document_query import DocumentQueryHelper


class DocumentQueryTool(Tool):

    async def execute(self, **kwargs):
        document_uri = kwargs.get("document")
        document_uris = []

        if isinstance(document_uri, list):
            document_uris = document_uri
        elif isinstance(document_uri, str):
            document_uris = [document_uri]

        queries = (
            kwargs["queries"]
            if "queries" in kwargs
            else [kwargs["query"]]
            if ("query" in kwargs and kwargs["query"])
            else []
        )

        # Get mode parameter (default to "text" for backward compatibility)
        mode = kwargs.get("mode", "text")
        if mode not in ("text", "visual", "auto"):
            mode = "text"

        # Get method parameter for management operations
        method = kwargs.get("method", "query")
        if method not in ("query", "list", "delete", "reindex"):
            method = "query"

        # For query operations, document is required
        if not document_uris and method == "query":
            return Response(message="Error: no document provided", break_loop=False)

        # Handle management operations (visual mode only)
        if method != "query":
            if mode == "text":
                return Response(
                    message="Error: Management methods (list/delete/reindex) only work with mode='visual'",
                    break_loop=False
                )

            # delete and reindex require documents
            if method in ("delete", "reindex") and not document_uris:
                return Response(message=f"Error: document required for {method}", break_loop=False)

            try:
                from python.helpers.visual_document_query import VisualDocumentQueryHelper

                progress = []
                def progress_callback(msg):
                    progress.append(msg)
                    self.log.update(progress="\n".join(progress))

                visual_helper = VisualDocumentQueryHelper(self.agent, progress_callback)

                if method == "list":
                    scope = kwargs.get("scope")  # Optional: "project", "global", or None
                    result = visual_helper.list_indexed_documents(scope)
                    return Response(message=result, break_loop=False)

                elif method == "delete":
                    results = []
                    for uri in document_uris:
                        result = await visual_helper.delete_indexed_document(uri)
                        results.append(result)
                    return Response(message="\n".join(results), break_loop=False)

                elif method == "reindex":
                    scope = kwargs.get("scope")
                    results = []
                    for uri in document_uris:
                        result = await visual_helper.reindex_indexed_document(uri, scope)
                        results.append(result)
                    return Response(message="\n".join(results), break_loop=False)

            except ImportError:
                return Response(
                    message="Error: Visual mode requires litepali. Install with: pip install litepali",
                    break_loop=False
                )
            except RuntimeError as e:
                return Response(
                    message=f"Error: {e}",
                    break_loop=False
                )

        try:
            progress = []

            def progress_callback(msg):
                progress.append(msg)
                self.log.update(progress="\n".join(progress))

            results = []

            # Text mode (original behavior)
            if mode in ("text", "auto"):
                text_helper = DocumentQueryHelper(self.agent, progress_callback)
                if not queries:
                    contents = await asyncio.gather(
                        *[text_helper.document_get_content(uri) for uri in document_uris]
                    )
                    text_content = "\n\n---\n\n".join(contents)
                else:
                    _, text_content = await text_helper.document_qa(document_uris, queries)

                if mode == "auto":
                    results.append("## Text Results\n\n" + text_content)
                else:
                    results.append(text_content)

            # Visual mode
            if mode in ("visual", "auto"):
                try:
                    from python.helpers.visual_document_query import VisualDocumentQueryHelper

                    visual_helper = VisualDocumentQueryHelper(self.agent, progress_callback)

                    if not queries:
                        # Get visual summary for each document
                        summaries = []
                        for uri in document_uris:
                            summary = await visual_helper.get_visual_summary(uri)
                            summaries.append(f"{uri}: {summary}")
                        visual_content = "\n".join(summaries)
                    else:
                        _, visual_content = await visual_helper.visual_document_qa(
                            document_uris, queries
                        )

                    if mode == "auto":
                        results.append("## Visual Results\n\n" + visual_content)
                    else:
                        results.append(visual_content)

                except ImportError:
                    if mode == "visual":
                        return Response(
                            message="Error: Visual mode requires litepali. Install with: pip install litepali",
                            break_loop=False
                        )
                    # In auto mode, just skip visual if not available
                    progress_callback("Visual mode not available (litepali not installed)")

            # Combine results
            if mode == "auto" and len(results) > 1:
                content = "\n\n---\n\n".join(results)
                content += "\n\n---\n*Note: Both text and visual analysis provided. Visual results may capture layout-dependent information that text extraction missed.*"
            else:
                content = results[0] if results else "No results"

            return Response(message=content, break_loop=False)

        except Exception as e:  # pylint: disable=broad-exception-caught
            return Response(message=f"Error processing document: {e}", break_loop=False)
