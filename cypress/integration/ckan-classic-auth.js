Cypress.on('uncaught:exception', (err, runnable) => {
  console.log(err);
  return false;
})

describe('No access for anonymous users', () => {
  it('Anonymous user cannot see the UI', () => {
    cy.clearCookies()
    cy.visit('/')
    cy.location().should((loc) => {
      expect(loc.pathname).to.eq('/user/login')
    })
  })

  it('Self registration is disabled', () => {
    cy.clearCookies()
    cy.request({url: '/user/register', failOnStatusCode: false}).then((resp) => {
      expect(resp.status).to.eq(403)
    })
  })
})


describe('Authorized users', () => {
  beforeEach(function(){
    cy.fixture('aircan.json').as('testData').then(() => {
      cy.login(this.testData.username, this.testData.password)
    })
  })

  it('Should Login Successfully', () => {
    cy.get('.username')
  })

  // it('Generate a new API key via UI', () => {
  //   cy.get('.list-unstyled > :nth-child(4) > a').click({force: true})
  //   cy.get('.btn-warning').click()
  //   cy.get('.modal-footer > .btn-primary').click()
  //   cy.contains('Profile updated')
  // })
})
