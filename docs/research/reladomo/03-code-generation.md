# The code generator turns one XML into a fixed set of Java artifacts via a JSP template engine; generated code is scaffolding over the runtime

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The generator is an Ant task (`generator/MithraGenerator.java`) delegating to `CoreMithraGenerator`.
The pipeline is **parse → validate → template**:

```text
generator/
├── MithraGenerator.java            # Ant task entry point
├── BaseMithraGenerator.java        # parse + validate orchestration
├── CoreMithraGenerator.java        # template dispatch + file writing
├── MithraXMLObjectTypeParser.java  # class-list + per-object XML parsing (parallel)
├── MithraObjectTypeWrapper.java    # rich in-memory model; drives template selection
├── metamodel/                      # FreyaXml-generated XML beans (MithraObjectType, AttributeType…)
├── queryparser/                    # JavaCC MithraQL parser for relationship predicates
│   └── ASTRelationalExpression.java  # validates types; emits constructEqualityMapper(...) calls
└── templates/                      # JSP templates by category
    ├── transactional/  (Abstract.jsp, Data.jsp, Finder.jsp, ListAbstract.jsp, DatabaseObjectAbstract.jsp, + concrete stubs)
    ├── readonly/  datedtransactional/  datedreadonly/  embeddedvalue/
```

1. **Parse** — `MithraXMLObjectTypeParser.parse()` (line 106) reads the class-list `<Mithra>` XML, then
   parallel-parses each referenced object file into a `MithraObjectTypeWrapper` (FreyaXml-generated
   `MithraGeneratorUnmarshaller`), tracking a CRC32 for change detection.
2. **Validate** — `BaseMithraGenerator.validateMithraObjectTypes()` (line 342): name checks, attribute
   resolution, superclass hierarchy sort, index validation, and `checkRelationships()` — which runs
   the JavaCC `MithraQL` parser on each predicate string to build `ASTRelationalExpression` trees and
   validate type compatibility.
3. **Template** — `CoreMithraGenerator.applyTemplates()` (line 224) selects a template list and package
   from static maps keyed by object type, then for each template instantiates the compiled `.jsp`
   (a class implementing `MithraTemplate`, `generator/MithraTemplate.java`) and calls
   `_jspService(request, response)` against a stub `HttpServletRequest` carrying the wrapper. The
   "servlet API" stubs (`generator/JspWriter.java`, `HttpServletRequest.java`) are a fiction enabling
   JSP syntax for codegen without a container.

The generated artifacts per (non-pure) object, and the scaffolding/runtime boundary:

| Artifact | Overwritten? | Inherits (runtime) | Role |
|---|---|---|---|
| `[Name]Abstract.java` | always | `MithraTransactionalObjectImpl` / read-only / dated variants | Typed getters/setters/relationships — **delegate to runtime state machine** |
| `[Name].java` | once | `[Name]Abstract` | Hand-written domain logic slot |
| `[Name]Data.java` | always | `MithraDataObject` | Plain data carrier for cache copy-on-write |
| `[Name]ListAbstract.java` | always | `AbstractTransactionalList` | Typed bulk ops + navigation |
| `[Name]List.java` | once | `[Name]ListAbstract` | Constructor stub |
| `[Name]Finder.java` | always | (static) | Holds the `MithraObjectPortal`, typed `Attribute` instances, indices |
| `[Name]DatabaseObjectAbstract.java` | always | `MithraDatabaseObject` subclass | Column binding, PK list, ResultSet inflation |
| `[Name]DatabaseObject.java` | once | `…Abstract` | Override slot |

Pure objects swap `DatabaseObject*` for `ObjectFactory*` (no SQL). The diagnostic for the boundary is
the `extends` clause in `templates/transactional/Abstract.jsp:55-70`: the generated abstract class is a
typed façade over `mithra/superclassimpl/MithraTransactionalObjectImpl`, where all persistence
behavior actually lives. "Once"-generated files survive regeneration (`replaceIfExists=false`),
routed to a source tree, while "always" files go to a build output dir.

## Testing patterns

Generator correctness is primarily validated indirectly: the entire `reladomo` test suite depends on
the committed pre-generated `.../test/domain/` classes. Direct validator tests are in
`reladomogenutil/src/test/.../generator/` (see §2).

## Code references

- `generator/MithraGenerator.java`, `BaseMithraGenerator.java`, `CoreMithraGenerator.java` (applyTemplates 224, generateJavaFile 415), `MithraXMLObjectTypeParser.java` (106), `MithraObjectTypeWrapper.java` (getObjectType 645)
- `generator/queryparser/ASTRelationalExpression.java` — relationship predicate parsing → mapper emission
- `generator/templates/` — `transactional/`, `readonly/`, `datedtransactional/`, `datedreadonly/`, `embeddedvalue/` (`Abstract.jsp` extends clause 55-70)
